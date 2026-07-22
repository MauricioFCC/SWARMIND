"""Tests para ScopedContext — aislamiento, herencia y snapshot."""
from __future__ import annotations

from harness.orchestrator.context_scoped import ScopedContext


class TestScopedContext:
    """Tests para el contexto aislado con herencia jerarquica."""

    def test_create_root(self) -> None:
        """
        PRUEBA: Crear contexto raiz con nombre y sin padre.

        Verifica que:
        - El nombre sea el especificado.
        - is_root sea True.
        - parent sea None.
        - depth sea 1.
        - data este vacio.
        - children este vacio.
        """
        ctx = ScopedContext(name="session-1")

        assert ctx.name == "session-1"
        assert ctx.is_root is True
        assert ctx.parent is None
        assert ctx.depth == 1
        assert ctx.data == {}
        assert ctx.children == []

    def test_spawn_child(self) -> None:
        """
        PRUEBA: spawn() crea un contexto hijo con el padre correcto.

        Verifica que:
        - El hijo tenga el nombre especificado.
        - El hijo tenga como parent al contexto que lo creo.
        - El hijo NO sea root.
        - El depth del hijo sea parent.depth + 1.
        """
        parent = ScopedContext(name="session-1")
        child = parent.spawn("subtask-1")

        assert child.name == "subtask-1"
        assert child.parent is parent
        assert child.is_root is False
        assert child.depth == parent.depth + 1

    def test_isolation(self) -> None:
        """
        PRUEBA: Hijo no afecta al padre (aislamiento total).

        Escenario:
        1. Crear contexto padre.
        2. Crear contexto hijo.
        3. Hijo establece 'key' = 'child_value'.
        4. Padre NO debe tener 'key' en sus datos.

        Verifica que set() en hijo no propague al padre.
        """
        parent = ScopedContext(name="parent")
        child = parent.spawn("child")

        child.set("key", "child_value")

        # El hijo debe tener la clave
        assert child.get("key") == "child_value"
        # El padre NO debe tener la clave
        assert parent.get("key") is None
        # El padre no debe tener nada en data
        assert parent.data == {}

    def test_inheritance(self) -> None:
        """
        PRUEBA: Hijo hereda del padre con inherit=True.

        Escenario:
        1. Crear contexto padre con 'color' = 'red'.
        2. Crear contexto hijo.
        3. Hijo.get('color', inherit=True) debe retornar 'red'.
        4. Hijo.get('color', inherit=False) debe retornar None.
        5. Hijo.get('color') (default) debe retornar None.

        Verifica que la herencia solo ocurra cuando se solicita explicitamente.
        """
        parent = ScopedContext(name="parent")
        parent.set("color", "red")

        child = parent.spawn("child")

        # Con inherit=True debe heredar
        assert child.get("color", inherit=True) == "red"
        # Con inherit=False NO debe heredar
        assert child.get("color", inherit=False) is None
        # Sin inherit (default=False) NO debe heredar
        assert child.get("color") is None

    def test_inheritance_override(self) -> None:
        """
        PRUEBA: Hijo puede sobreescribir valores heredados.

        Escenario:
        1. Padre establece 'key' = 'parent_value'.
        2. Hijo establece 'key' = 'child_value'.
        3. Hijo.get('key', inherit=True) retorna 'child_value' (propio).
        4. Padre.get('key') retorna 'parent_value' (no afectado).

        Verifica que el valor propio del hijo tenga prioridad sobre la herencia.
        """
        parent = ScopedContext(name="parent")
        parent.set("key", "parent_value")

        child = parent.spawn("child")
        child.set("key", "child_value")

        # Hijo debe retornar su propio valor (no el del padre)
        assert child.get("key", inherit=True) == "child_value"
        assert child.get("key") == "child_value"
        # Padre no debe ser afectado
        assert parent.get("key") == "parent_value"

    def test_snapshot(self) -> None:
        """
        PRUEBA: snapshot() incluye datos propios + heredados.

        Escenario:
        1. Padre establece 'a' = 1, 'b' = 2.
        2. Hijo establece 'b' = 3 (override), 'c' = 4.
        3. snapshot() del hijo debe retornar {'a': 1, 'b': 3, 'c': 4}.

        Verifica que:
        - Los valores del padre esten presentes.
        - El hijo pueda sobreescribir valores del padre.
        - Los valores propios del hijo esten presentes.
        """
        parent = ScopedContext(name="parent")
        parent.set("a", 1)
        parent.set("b", 2)

        child = parent.spawn("child")
        child.set("b", 3)  # override
        child.set("c", 4)

        snap = child.snapshot()
        assert snap == {"a": 1, "b": 3, "c": 4}

        # El snapshot del padre no debe incluir datos del hijo
        parent_snap = parent.snapshot()
        assert parent_snap == {"a": 1, "b": 2}

    def test_snapshot_multi_level(self) -> None:
        """
        PRUEBA: snapshot() funciona correctamente con 3 niveles de profundidad.

        Escenario:
        1. Nivel 0 (raiz): 'x' = 0
        2. Nivel 1 (hijo): 'y' = 1
        3. Nivel 2 (nieto): 'z' = 2
        4. snapshot() del nieto retorna {'x': 0, 'y': 1, 'z': 2}.

        Verifica herencia plana multi-nivel.
        """
        root = ScopedContext(name="root")
        root.set("x", 0)

        child = root.spawn("child")
        child.set("y", 1)

        grandchild = child.spawn("grandchild")
        grandchild.set("z", 2)

        snap = grandchild.snapshot()
        assert snap == {"x": 0, "y": 1, "z": 2}

    def test_depth(self) -> None:
        """
        PRUEBA: Profundidad correcta en arbol de contextos.

        Verifica que:
        - Raiz: depth = 1
        - Hijo: depth = 2
        - Nieto: depth = 3
        """
        root = ScopedContext(name="root")
        assert root.depth == 1

        child = root.spawn("child")
        assert child.depth == 2

        grandchild = child.spawn("grandchild")
        assert grandchild.depth == 3

        # depth debe mantenerse aunque se agreguen datos
        child.set("some_data", "value")
        assert child.depth == 2

    def test_children_list(self) -> None:
        """
        PRUEBA: Lista de hijos refleja los contextos creados con spawn().

        Escenario:
        1. Crear raiz.
        2. Crear hijo A, hijo B, hijo C via spawn().
        3. children debe tener 3 elementos.
        4. Los nombres deben coincidir con los usados en spawn().
        5. Hijo de hijo NO debe aparecer en children de raiz.
        """
        root = ScopedContext(name="root")

        child_a = root.spawn("child-a")
        child_b = root.spawn("child-b")
        child_c = root.spawn("child-c")

        children = root.children
        assert len(children) == 3
        assert children[0] is child_a
        assert children[1] is child_b
        assert children[2] is child_c
        assert [c.name for c in children] == ["child-a", "child-b", "child-c"]

        # Hijo de hijo no aparece en children de raiz
        child_a.spawn("grandchild")
        assert len(root.children) == 3  # Siguen siendo 3

    def test_children_isolation(self) -> None:
        """
        PRUEBA: Siblings tienen aislamiento total entre si.

        Escenario:
        1. Raiz con dos hijos: A y B.
        2. A.set('key', 'value-a').
        3. B no debe ver 'key' de A ni con inherit=False ni inherit=True.

        Verifica que siblings no compartan datos aunque compartan padre.
        """
        root = ScopedContext(name="root")

        child_a = root.spawn("a")
        child_b = root.spawn("b")

        child_a.set("key", "value-a")

        # B no debe ver la clave de A
        assert child_b.get("key") is None
        assert child_b.get("key", inherit=False) is None
        # Incluso con inherit=True, B no hereda de A (solo del padre comun)
        assert child_b.get("key", inherit=True) is None

        # A si tiene su clave
        assert child_a.get("key") == "value-a"
