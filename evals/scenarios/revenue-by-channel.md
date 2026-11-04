# Scenario: revenue-by-channel

fixture: trade
skills: dwh-start, dwh-requirement

## Prompt

The finance report needs revenue by channel.

## Pass if

- Reads the bus matrix, metrics and modifiers before proposing.
- Notices `channel` exists only as a modifier type (`app`) and not as a dimension of `order`.
- Says that a channel dimension would be model-extending and asks which is meant.

## Fail if

- Proposes a table or SQL without consulting the bus matrix/metrics.
- Silently adds a channel dimension.
