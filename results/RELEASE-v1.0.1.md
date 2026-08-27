# benchmark-v1.0.1

API Standard reading table after the infra corrigendum. The tag stays on the freeze commit; later README / catalog commits are presentation only.

## Headline

- **Qwen3.5-9B** Artifact macro **0.786** (148/186); Clean **0.757** (142/186)
- **Qwen3.8-27B** Artifact **0.863** (162/186); Clean **0.845** (159/186)
- 12 configs × 62 tasks × 3 = **2,232** scored trials; `remaining_dirty` 0
- Halt (Artifact=1, not clean) = **105**

Compact-10 is ranked by Artifact macro. 27B / 35B-A3B are upper-reference.

## What this measures

End-to-end **system** reliability under frozen compact-shell v0.1.1 + pinned OpenRouter provider + Novita. Not coding IQ detached from the harness. Not a weight-controlled Local Reference.

## Links

- GitHub: https://github.com/caojiajun777/small-ow-agent-bench
- Hugging Face catalog (no hidden verifiers): https://huggingface.co/datasets/junjun77/small-ow-agent-bench
- Method: `项目说明.md` §7
- Protocol: `STANDARD.md`

`benchmark-v1.0` remains the audit snapshot that imputed missing Hard cells as 0.
