"""Estrategias de debate multi-agente (extraccion mecanica).

Mixin privado con la implementacion de las estrategias CONSENSUS,
CRITIQUE y DELIBERATION, incluyendo la variante asincrona (PaCoRe).
"""
from __future__ import annotations

from .models import DebateResult, DebateRound, DebateStrategy, DispatchFn


class _StrategiesMixin:
    """Estrategias de debate usadas por DebateOrchestrator."""
    def _execute_consensus(
        self,
        task: str,
        agents: list[str],
        max_rounds: int,
        dispatch_fn: DispatchFn,
        session_id: str,
    ) -> DebateResult:
        """All agents produce answers independently, then vote (conference)."""
        rounds: list[DebateRound] = []
        all_outputs: dict[str, str] = {}

        # --- Round 1: Independent answers ---
        round1 = DebateRound(round_num=1)
        for agent in agents:
            context = {
                "strategy": DebateStrategy.CONSENSUS.value,
                "round": 1,
                "previous_outputs": dict(all_outputs),
                "feedback": {},
                "phase": "independent_answer",
            }
            output = dispatch_fn(agent, task, context)
            round1.agent_outputs[agent] = output
            all_outputs[agent] = output

            # Log via AgentBus
            self._log_agent_message(session_id, agent, task, output, round_num=1)

        # Round 1 confidence: how much do initial answers agree?
        round1.confidence = self._compute_agreement(round1.agent_outputs)
        round1.synthesis = self._synthesize_answers(round1.agent_outputs)
        rounds.append(round1)

        # --- Round 2 (if max_rounds > 1): Conference / Voting ---
        if max_rounds >= 2:
            round2 = DebateRound(round_num=2)

            # Each agent reviews all other answers
            for agent in agents:
                other_outputs = {
                    a: out for a, out in all_outputs.items() if a != agent
                }
                conference_context = {
                    "strategy": DebateStrategy.CONSENSUS.value,
                    "round": 2,
                    "previous_outputs": dict(all_outputs),
                    "feedback": {},
                    "phase": "conference_vote",
                    "other_answers": other_outputs,
                }
                vote = dispatch_fn(agent, task, conference_context)
                round2.critique_feedback[agent] = vote

            # Determine winner by similarity clustering
            winner_output, winner_agreement = self._majority_winner(all_outputs)

            round2.synthesis = (
                f"Consenso tras conferencia: {winner_output[:200]}"
            )
            round2.confidence = winner_agreement
            rounds.append(round2)

        else:
            # Single round â€” pick best by agreement directly
            winner_output, winner_agreement = self._majority_winner(all_outputs)

        # Determine final answer
        if max_rounds >= 2:
            final_answer = rounds[-1].synthesis
        else:
            final_answer = winner_output

        # Overall confidence: average of round confidences
        overall_confidence = (
            sum(r.confidence for r in rounds) / len(rounds) if rounds else 0.0
        )

        # Agent agreement: how aligned were agents in the final round
        final_agreement = rounds[-1].confidence if rounds else 0.0

        return DebateResult(
            session_id=session_id,
            task=task,
            strategy=DebateStrategy.CONSENSUS,
            rounds=rounds,
            final_answer=final_answer,
            confidence=overall_confidence,
            agent_agreement=final_agreement,
            metadata={
                "num_agents": len(agents),
                "num_rounds": len(rounds),
                "agents": list(agents),
                "strategy": DebateStrategy.CONSENSUS.value,
            },
        )

    async def _execute_consensus_async(
        self,
        task: str,
        agents: list[str],
        max_rounds: int,
        dispatch_fn: callable,
        session_id: str,
    ) -> DebateResult:
        """
        Version asincrona de consenso: agentes responden en paralelo.

        Usa asyncio.gather para ejecutar dispatch de todos los agentes
        simultaneamente, reduciendo latencia de O(n) a O(1).

        Args:
            task: Tarea a debatir.
            agents: Lista de agentes.
            max_rounds: Maximo de rondas.
            dispatch_fn: Funcion de dispatch.
            session_id: ID de sesion.

        Returns:
            DebateResult con respuestas de todos los agentes.
        """
        import asyncio

        responses: list[str] = []
        rounds: list[DebateRound] = []
        for rnd in range(max_rounds):
            round_responses = await asyncio.gather(
                *[self._run_async_dispatch(agent, task, dispatch_fn)
                  for agent in agents],
                return_exceptions=True,
            )
            valid = [r for r in round_responses if isinstance(r, str)]
            if not valid:
                break
            responses.extend(valid)

            dr = DebateRound(round_num=rnd + 1)
            for i, agent in enumerate(agents):
                if i < len(valid):
                    dr.agent_outputs[agent] = valid[i]
            dr.confidence = self._compute_agreement(dict(dr.agent_outputs))
            dr.synthesis = self._synthesize_answers(dict(dr.agent_outputs))
            rounds.append(dr)

            # Verificar convergencia temprana
            if len(valid) == len(agents) and dr.confidence > 0.9:
                break

        return DebateResult(
            session_id=session_id,
            task=task,
            strategy=DebateStrategy.CONSENSUS,
            rounds=rounds,
            final_answer=responses[-1] if responses else "",
            confidence=0.85,
            agent_agreement=rounds[-1].confidence if rounds else 0.0,
            metadata={
                "num_agents": len(agents),
                "num_rounds": len(rounds),
                "agents": list(agents),
                "strategy": DebateStrategy.CONSENSUS.value,
                "async": True,
            },
        )

    async def _run_async_dispatch(
        self,
        agent: str,
        task: str,
        dispatch_fn: callable,
    ) -> str:
        """
        Ejecutar dispatch de un agente de forma asincrona.

        Args:
            agent: Nombre del agente.
            task: Tarea a ejecutar.
            dispatch_fn: Funcion de dispatch.

        Returns:
            Respuesta del agente.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, dispatch_fn, agent, task)

    def _execute_critique(
        self,
        task: str,
        agents: list[str],
        max_rounds: int,
        dispatch_fn: DispatchFn,
        session_id: str,
    ) -> DebateResult:
        """Primary agent produces an answer, secondary agent critiques, then refinement."""
        rounds: list[DebateRound] = []
        primary = agents[0]
        critic = agents[1] if len(agents) > 1 else agents[0]
        refiners = agents[2:] if len(agents) > 2 else []

        # --- Round 1: Primary agent produces answer ---
        round1 = DebateRound(round_num=1)
        context_r1 = {
            "strategy": DebateStrategy.CRITIQUE.value,
            "round": 1,
            "previous_outputs": {},
            "feedback": {},
            "phase": "primary_answer",
        }
        primary_output = dispatch_fn(primary, task, context_r1)
        round1.agent_outputs[primary] = primary_output
        self._log_agent_message(session_id, primary, task, primary_output, round_num=1, phase="primary")

        outputs_so_far: dict[str, str] = {primary: primary_output}
        feedback_so_far: dict[str, str] = {}

        # Round 1 confidence: baseline
        round1.confidence = 0.5
        rounds.append(round1)

        # --- Round 2: Critique ---
        if max_rounds >= 2:
            round2 = DebateRound(round_num=2)
            critique_context = {
                "strategy": DebateStrategy.CRITIQUE.value,
                "round": 2,
                "previous_outputs": dict(outputs_so_far),
                "feedback": {},
                "phase": "critique",
                "answer_to_review": primary_output,
            }
            critique = dispatch_fn(critic, task, critique_context)
            round2.critique_feedback[critic] = critique
            feedback_so_far[critic] = critique
            self._log_agent_message(session_id, critic, task, critique, round_num=2, phase="critique")
            round2.confidence = 0.4  # critique phase â€” lower confidence
            rounds.append(round2)

        # --- Round 3 (optional): Refinement by primary ---
        has_refinement = max_rounds >= 3 or refiners
        if has_refinement:
            refiner = refiners[0] if refiners else primary
            round3 = DebateRound(round_num=3)
            refine_context = {
                "strategy": DebateStrategy.CRITIQUE.value,
                "round": 3,
                "previous_outputs": dict(outputs_so_far),
                "feedback": dict(feedback_so_far),
                "phase": "refinement",
                "original_answer": primary_output,
                "critique": feedback_so_far.get(critic, ""),
            }
            refined = dispatch_fn(refiner, task, refine_context)
            round3.agent_outputs[refiner] = refined
            outputs_so_far[refiner] = refined
            self._log_agent_message(session_id, refiner, task, refined, round_num=3, phase="refinement")

            # Check if critique was addressed (agreement improvement)
            addressed = self._critique_addressed(primary_output, refined, feedback_so_far.get(critic, ""))
            round3.confidence = 0.7 if addressed else 0.4
            round3.synthesis = refined
            rounds.append(round3)

        # Final answer: best available
        if has_refinement:
            final_answer = rounds[-1].agent_outputs.get(
                next(iter(rounds[-1].agent_outputs.keys())),
                rounds[-1].synthesis or primary_output,
            )
        else:
            final_answer = primary_output

        overall_confidence = (
            sum(r.confidence for r in rounds) / len(rounds) if rounds else 0.0
        )

        return DebateResult(
            session_id=session_id,
            task=task,
            strategy=DebateStrategy.CRITIQUE,
            rounds=rounds,
            final_answer=final_answer,
            confidence=overall_confidence,
            agent_agreement=overall_confidence,
            metadata={
                "num_agents": len(agents),
                "num_rounds": len(rounds),
                "agents": list(agents),
                "primary_agent": primary,
                "critic_agent": critic,
                "strategy": DebateStrategy.CRITIQUE.value,
            },
        )

    def _execute_deliberation(
        self,
        task: str,
        agents: list[str],
        max_rounds: int,
        dispatch_fn: DispatchFn,
        session_id: str,
    ) -> DebateResult:
        """Sequential debate where each agent builds on the previous output."""
        rounds: list[DebateRound] = []
        outputs_so_far: dict[str, str] = {}
        num_agents = len(agents)

        for i, agent in enumerate(agents):
            if i >= max_rounds:
                break

            round_i = DebateRound(round_num=i + 1)
            context = {
                "strategy": DebateStrategy.DELIBERATION.value,
                "round": i + 1,
                "previous_outputs": dict(outputs_so_far),
                "feedback": {},
                "phase": "deliberation",
                "agent_index": i,
                "total_agents": num_agents,
            }

            output = dispatch_fn(agent, task, context)
            round_i.agent_outputs[agent] = output
            outputs_so_far[agent] = output
            self._log_agent_message(session_id, agent, task, output, round_num=i + 1, phase="deliberation")

            # Confidence increases as more agents contribute
            progress = (i + 1) / num_agents
            round_i.confidence = 0.3 + (progress * 0.5)
            round_i.synthesis = output

            rounds.append(round_i)

        # Final round's output is the synthesized answer
        final_round = rounds[-1] if rounds else DebateRound(round_num=0)
        final_answer = final_round.synthesis or (
            next(iter(final_round.agent_outputs.values()))
            if final_round.agent_outputs else ""
        )

        overall_confidence = (
            sum(r.confidence for r in rounds) / len(rounds) if rounds else 0.0
        )

        # Agreement: how consistent were the outputs across rounds
        texts = [r.synthesis or next(iter(r.agent_outputs.values()), "") for r in rounds]
        pairwise_similarities = []
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                pairwise_similarities.append(
                    self._text_similarity(texts[i], texts[j])
                )
        agreement = (
            sum(pairwise_similarities) / len(pairwise_similarities)
            if pairwise_similarities else 0.0
        )

        return DebateResult(
            session_id=session_id,
            task=task,
            strategy=DebateStrategy.DELIBERATION,
            rounds=rounds,
            final_answer=final_answer,
            confidence=overall_confidence,
            agent_agreement=agreement,
            metadata={
                "num_agents": len(agents),
                "num_rounds": len(rounds),
                "agents": list(agents),
                "strategy": DebateStrategy.DELIBERATION.value,
            },
        )
