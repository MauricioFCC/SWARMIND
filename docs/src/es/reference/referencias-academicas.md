# Referencias Académicas — Swarmind

> Documento generado tras inspección de 32 ADRs. Cada paper fue verificado directamente en arXiv para confirmar autores, título y año.

---

## Papers Implementados (16)

### Memoria y RAG

- [Yang, N., Li, S., Shen, M., Zhou, Y., Zhang, M., Li, T., & Zhang, H. (2026). *SF-AMS: Strategic Forgetting for Structured Memory in LLM Agent*. arXiv:2607.22562.](https://arxiv.org/abs/2607.22562)
- [Jiang, E. H., Zhang, Z., Wu, Y., Li, L., Liu, D., Liang, X., Sun, R., Li, Y., Sun, E., Luo, H., Kang, Z., Caliskan, A., Chang, K.-W., & Wu, Y. N. (2026). *Memory as a Controlled Process: Learned Adaptive Memory Management for LLM Agents*. arXiv:2607.13591.](https://arxiv.org/abs/2607.13591)
- [Zhu, D., Zheng, L. N., & Chen, Z. (2026). *FundaPod: A Multi-Persona Agent Pod Platform with Knowledge Graph Memory for AI-Assisted Fundamental Investment Research*. arXiv:2605.27864.](https://arxiv.org/abs/2605.27864)

### Orquestación y Paralelismo

- [Koh, J. Y., Salakhutdinov, R., & Fried, D. (2026). *Multi-Agent Computer Use*. arXiv:2606.01533.](https://arxiv.org/abs/2606.01533)
- [Wagenländer, M., White, O., Jarrett, B., Silvestre, P., Tao, Y., Li, G., Zhu, H., Vilanova, L., & Pietzuch, P. (2026). *Scepsy: Serving Swarmind Workflows Using Aggregate LLM Pipelines*. arXiv:2604.15186.](https://arxiv.org/abs/2604.15186)
- [Ray, A. (2026). *Agent Capsules: Quality-Gated Granularity Control for Multi-Agent LLM Pipelines*. arXiv:2605.00410.](https://arxiv.org/abs/2605.00410)

### Seguridad y Gobernanza

- [Ravindran, A., & Deochake, S. (2026). *ToolGuardian: Declarative Security for AI Agent-Tool Interactions*. arXiv:2607.21835.](https://arxiv.org/abs/2607.21835)
- [Chen, S. (2026). *Governance Decay: How Context Compaction Silently Erases Safety Constraints in Long-Horizon LLM Agents*. arXiv:2606.22528.](https://arxiv.org/abs/2606.22528)
- [Fan, W., Nie, X., & Dai, Z. (2026). *Harness-MU: A Safe, Governed, and Effective Harness for Multi-User LLM Agents*. arXiv:2606.21856.](https://arxiv.org/abs/2606.21856)
- [Chen, H., Song, X., Jin, J., Ren, P., & Zhang, L.-J. (2026). *Toward an Organizational Science of Multi-Agent LLM Systems: Decoupling Who, How, and Which Algorithm*. arXiv:2607.25446.](https://arxiv.org/abs/2607.25446)

### Creatividad y Pensamiento Divergente

- [Park, J., Baek, I., Park, J., & Lee, H. (2026). *Beyond One Path: Evaluating and Enhancing Divergent Thinking in Interactive LLM Agents*. arXiv:2605.28465.](https://arxiv.org/abs/2605.28465)
- [Chen, N., Tong, Y., Yang, Y., He, Y., Zhang, X., Zou, Q., Wang, Q., & He, B. (2026). *Diversity Collapse in Multi-Agent LLM Systems: Structural Coupling and Collective Failure in Open-Ended Idea Generation*. arXiv:2604.18005.](https://arxiv.org/abs/2604.18005)

### Optimización de Tokens y Costos

- [Owusu Agyemang, J., Kponyo, J. J., Amponsah, E., Addo Boakye, G. M., & Opuni-Boachie Obour Agyekum, K. (2026). *Local-Splitter: A Measurement Study of Seven Tactics for Reducing Cloud LLM Token Usage on Coding-Agent Workloads*. arXiv:2604.12301.](https://arxiv.org/abs/2604.12301)

### Herramientas y Lenguaje Natural

- [Somma, A., Plante, I., & Premji, F. (2026). *The Remarkable Effectiveness of Providing AI Agents with Natural Language Tools: A Replication Study Validating NLT Performance Across 14 Models*. arXiv:2607.03953.](https://arxiv.org/abs/2607.03953)

### Meta-Aprendizaje y Testing

- [Xia, P., Chen, J., Yang, X., Tu, H., Liu, J., Xiong, K., Han, S., Qiu, S., Ji, H., Zhou, Y., Zheng, Z., Xie, C., & Yao, H. (2026). *MetaClaw: Just Talk — An Agent That Meta-Learns and Evolves in the Wild*. arXiv:2603.17187.](https://arxiv.org/abs/2603.17187)
- [Maaz, M., DeVoe, L., Hatfield-Dodds, Z., & Carlini, N. (2025). *Swarmind Property-Based Testing: Finding Bugs Across the Python Ecosystem*. arXiv:2510.09907.](https://arxiv.org/abs/2510.09907)

---

## Herramientas Open Source

| Herramienta | Licencia | Propósito en Swarmind |
|-------------|----------|----------------------|
| [LanceDB](https://lancedb.github.io/) | Apache 2.0 | Vector store principal (embeddings persistentes) |
| [Chroma](https://www.trychroma.com/) | Apache 2.0 | Vector store secundario (benchmarking y federación) |
| [Hypothesis](https://hypothesis.works/) | MPL 2.0 | Property-based testing (PBT Core, Swarmind PBT) |
| [pytest](https://pytest.org/) | MIT | Framework de testing (3420 tests) |
| [PyTorch](https://pytorch.org/) | BSD-3 | GPU acceleration, embeddings |
| [Qdrant](https://qdrant.tech/) | Apache 2.0 | Vector store terciario (federated search) |
| [SQLite-vec](https://github.com/asg017/sqlite-vec) | Apache 2.0 | Vector store edge/offline (sin dependencias) |
| [OpenTelemetry](https://opentelemetry.io/) | Apache 2.0 | Observabilidad (trazas, métricas, exportación OTLP) |
| [NumPy](https://numpy.org/) | BSD-3 | Álgebra lineal, kernels de similitud |
| [PyYAML](https://pyyaml.org/) | MIT | Configuración declarativa de skills y agentes |

---

## Licencia MIT

```
MIT License

Copyright (c) 2026 Swarmind

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Créditos

Agradecimientos a los autores de los papers implementados, especialmente a Ning Yang, Arun Ravindran, Saurabh Deochake, Jing Yu Koh, Shiyang Chen, Aninda Ray, Marcel Wagenländer, Di Zhu, Justice Owusu Agyemang, Jihyeong Park, Nuo Chen, Muhammad Maaz, Alexander Somma, Wangxuan Fan, Huan Chen, Eric Hanchen Jiang y Peng Xia por su investigación pionera en sistemas multi-agente 2026.

A los mantenedores de LanceDB, Chroma, Hypothesis (Zac Hatfield-Dodds y equipo), pytest, PyTorch (Meta AI), Qdrant, OpenTelemetry y NumPy por su infraestructura open source fundamental.
