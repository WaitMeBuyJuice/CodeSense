
## 上下游详表

| 模块 | 上游（依赖于我） | 下游（我依赖） |
|------|----------------|--------------|
| cache | summarizer、tools | 无 |
| data | summarizer、tools | 无 |
| errors | registry、summarizer、tools | 无 |
| registry | server、tools | errors |
| server | 无 | registry |
| summarizer | tools | cache、data、errors |
| tools | 无 | cache、data、errors、registry、summarizer |

> 无循环依赖。