# AuditHound compatibility

Make MCP contains no AuditHound-specific types or scanner abstractions.

An external consumer such as AuditHound can use the generic surfaces already provided:

- `list_tasks`
- `describe_task`
- `run_task`
- capability mappings
- declared path variables
- risk metadata
- timeout and bounded output
- stable `TaskResult`
- doctor diagnostics

Evidence, findings, scanner parsers and audit profiles belong in the consuming application. A generic output-artifact declaration should only be added if real integrations prove ordinary declared report-path variables insufficient.
