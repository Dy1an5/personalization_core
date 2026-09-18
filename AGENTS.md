# 项目简介

通用的 memory 和用户画像核心

# 操作

每次操作前查看 plan.md

plan.md 里有文件骨架, 数据结构和详细步骤, 严格按照好 plan.md执行

# Development workflow

For non-trivial code changes, the primary agent acts as the
architect and coordinator.

Always follow this sequence:

## Phase 1: Explore

Delegate codebase exploration to `code_reader`.

The primary agent should avoid performing broad codebase exploration
itself when `code_reader` can gather the required context.

Ask `code_reader` to identify:

- relevant files
- execution flow
- existing interfaces and models
- dependencies
- tests
- architectural constraints

Wait for its result before designing the implementation.

## Phase 2: Design

The primary agent owns the design.

Using the user's requirements and the report from `code_reader`,
produce a concrete implementation plan.

The plan must define where applicable:

- files to modify or create
- classes and objects
- data models and fields
- function and method signatures
- responsibilities
- control/data flow
- error behavior
- test changes

Do not delegate architectural decisions to `implementer`.

## Phase 3: Implement

After the design is complete, delegate implementation to `implementer`.

Provide the complete implementation plan and relevant constraints.

`implementer` owns:

- editing files
- creating files
- implementation
- tests
- lint/type checks
- fixing implementation errors

The primary agent should not duplicate implementation work.

## Phase 4: Review

After `implementer` finishes:

- inspect the implementation summary
- inspect important diffs when necessary
- verify that the implementation matches the design

If fixes are required, send explicit correction instructions back to
`implementer`.

Do not redesign the architecture unless new evidence requires it.
