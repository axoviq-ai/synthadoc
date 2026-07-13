---
aliases: []
confidence: high
created: 2026-04-08
lint_warnings:
- claim: The stored-program concept in von Neumann architecture directly implements
 alan-turing's theoretical Turing machine in physical hardware.
 concern: Turing's 1936 paper introduced an abstract mathematical model of computation
 and predates von Neumann's 1945 First Draft. While there are historical connections
 (e.g., Turing's involvement at Manchester and the ACE design), the stored-program
 concept was developed independently by multiple groups and is not a direct implementation
 of the Turing machine, which is a theoretical model not tied to any specific physical
 architecture.
- claim: The Von Neumann architecture, described in John von Neumann's 1945 'First
 Draft of a Report on the EDVAC,' is the design that underlies virtually every
 general-purpose computer built since.
 concern: Modern CPUs universally use Harvard-style caches, separate instruction
 and data pipelines, and other modifications that technically violate pure von
 Neumann architecture. Additionally, many embedded systems and GPUs use Harvard
 architecture. The claim that the von Neumann architecture underlies 'virtually
 every general-purpose computer' is an oversimplification of a more nuanced reality.
orphan: false
sources:
- file: public-domain/vonneumann-firstdraft-1945.txt
 hash: placeholder
 ingested: 2026-04-08
 size: 0
- file: C:\Users\ladmin\wikis\history-of-computing\raw_sources\public-domain\vonneumann-firstdraft-1945.txt
 hash: 8f5d3f50c56811dc7d5df0b6994449d09cf61b3c80b95bbd7456304a0d0058e3
 ingested: '2026-07-12'
 size: 5694
status: active
tags:
- architecture
- hardware
- stored-program
title: Von Neumann Architecture
type: technology
updated: '2026-07-12'
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

## Origins: The First Draft and the EDVAC

The "First Draft of a Report on the EDVAC" was written by john-von-neumann in the spring of 1945 as a consultant to the EDVAC project at the Moore School of Electrical Engineering at the University of Pennsylvania. EDVAC was conceived as a successor to eniac, and John Mauchly and J. Presper Eckert had been developing the design since 1944. Von Neumann distilled the collective design discussions into the First Draft, which was circulated internally and spread rapidly among researchers. ^[vonneumann-firstdraft-1945.txt:3-9]

The sole attribution to von Neumann has been disputed — Eckert and Mauchly and subsequent historians have argued that many of the ideas originated in group discussions. Nevertheless, the term **von Neumann architecture** persisted because the First Draft was the document that codified and propagated the design. ^[vonneumann-firstdraft-1945.txt:9-9]

## The Fetch-Decode-Execute Cycle

The fundamental operating cycle of a von Neumann machine repeats continuously:

1. **Fetch** — the control unit reads the instruction stored at the address given by the program counter.
2. **Decode** — the control unit interprets the binary instruction to determine the operation and its operands.
3. **Execute** — the control unit directs the ALU or another unit to perform the operation.
4. **Increment** — the program counter advances to the next instruction.

Conditional branches — instructions that update the program counter to a non-sequential address based on a computed result — provide the mechanism for loops and decisions. The speed of this cycle, measured in clock cycles per second, became the primary metric for processor performance for decades. ^[vonneumann-firstdraft-1945.txt:33-40]

## Influence and Legacy

The First Draft shaped the design of early computers across the United States and Britain. The IAS machine at Princeton, built by von Neumann's team beginning in 1945, was the first computer constructed directly to this specification. Clones of the IAS machine were subsequently built at universities and research laboratories throughout the world in the late 1940s and 1950s. Every programming language — from assembly code to modern high-level languages — ultimately targets the instruction set of a von Neumann machine. ^[vonneumann-firstdraft-1945.txt:44-46]

## Limitations and Extensions

The **von Neumann bottleneck** — the single bus connecting the CPU to memory that constrains throughput — was identified as a performance limit as early as the 1970s. Modern processor designs mitigate it through caches, multiple memory banks, out-of-order execution, and specialised co-processors, but the fundamental stored-program architecture remains the dominant paradigm. Alternative models such as dataflow architectures and neuromorphic computing have been explored, but none has displaced the von Neumann machine for general-purpose workloads. ^[vonneumann-firstdraft-1945.txt:50-50]

## Attribution Dispute

The sole attribution of the stored-program architecture to von Neumann has been disputed. [[john-presper-eckert|Eckert]] and [[john-william-mauchly|Mauchly]] — who had been working on the [[edvac|EDVAC]] concept since 1944 — pointed out that many of the ideas in the First Draft emerged from collective design discussions at the [[moore-school-of-electrical-engineering|Moore School]]. Subsequent historians have echoed this view. Nevertheless, the term "von Neumann architecture" has persisted because the First Draft was the document that codified and propagated the design to the wider research community.^[vonneumann-firstdraft-1945.txt:9-9]

## The Fetch-Decode-Execute Cycle

The fundamental operating cycle of a von Neumann machine is:

1. **Fetch** — the control unit reads the instruction stored at the address given by the program counter.
2. **Decode** — the control unit interprets the binary instruction to determine the operation and its operands.
3. **Execute** — the control unit directs the ALU or another unit to perform the operation.
4. **Increment** — the program counter advances to the next instruction.

This cycle repeats continuously. Conditional branches — instructions that update the program counter to a non-sequential address based on a computed result — provide the mechanism for loops and decisions. The speed at which this cycle executes, measured in clock cycles per second, became the primary metric by which processor performance was judged for decades.^[vonneumann-firstdraft-1945.txt:40-40]

## Influence on Computer Design

The First Draft circulated widely and shaped the design of early computers across the United States and Britain. The IAS machine at Princeton, built by von Neumann's team starting in 1945, was the first computer constructed directly to this specification. Clones of the IAS machine were built at universities and research laboratories throughout the world in the late 1940s and 1950s.^[vonneumann-firstdraft-1945.txt:44-44]

[[alan-turing|Alan Turing]]'s earlier theoretical Turing machine shares the same conceptual foundation — the idea that an abstract machine with a finite description can compute any computable function — but the First Draft provided the engineering blueprint rather than the mathematical abstraction. Every programming language ultimately targets the instruction set of a von Neumann machine.^[vonneumann-firstdraft-1945.txt:46-46]

## Limitations and Extensions

The **von Neumann bottleneck** — the single bus connecting the CPU to memory, which constrains throughput — was identified as a performance limit as early as the 1970s. Modern processor designs address this through caches, multiple memory banks, out-of-order execution, and specialised co-processors, but the fundamental stored-program architecture remains the dominant paradigm. Alternative models such as dataflow architectures and neuromorphic computing have been explored, but none has displaced the von Neumann machine for general-purpose workloads.^[vonneumann-firstdraft-1945.txt:50-50]