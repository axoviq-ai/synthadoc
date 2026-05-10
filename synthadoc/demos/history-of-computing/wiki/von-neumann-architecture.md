---
title: Von Neumann Architecture
tags: [architecture, hardware, stored-program]
status: active
confidence: high
created: 2026-04-08
sources:
  - file: public-domain/vonneumann-firstdraft-1945.txt
    hash: placeholder
    size: 0
    ingested: 2026-04-08
aliases: []
---

# Von Neumann Architecture

The Von Neumann architecture, described in John von Neumann's 1945 "First Draft of a Report on the EDVAC," is the design that underlies virtually every general-purpose computer built since. Its defining characteristic is that both program instructions and data reside in the same memory, allowing programs to be stored and modified like data.

## Core Components

1. **Central Processing Unit (CPU)** — fetches, decodes, and executes instructions
2. **Memory** — stores both data and program instructions in the same address space
3. **Input/Output** — mechanisms to communicate with the outside world
4. **Control Unit** — directs the flow of data between CPU and memory
5. **Arithmetic Logic Unit (ALU)** — performs arithmetic and bitwise operations

## Fetch-Decode-Execute Cycle

The CPU operates in a continuous loop: fetch the next instruction from memory, decode it, execute it, and increment the program counter. This cycle, often running billions of times per second in modern processors, is the heartbeat of every program.

## Relationship to Turing's Work

The stored-program concept in von Neumann architecture directly implements [[alan-turing]]'s theoretical Turing machine in physical hardware. Where Turing described computation abstractly, von Neumann specified the engineering blueprint.

## Influence on Operating Systems

When Ken Thompson and Dennis Ritchie designed [[unix-history]], they targeted a von Neumann machine (the PDP-7). Every [[programming-languages-overview]] language ultimately compiles down to machine code that runs on this architecture.
