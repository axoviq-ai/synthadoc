---
aliases: []
confidence: high
created: 2026-04-08
orphan: false
sources:
- file: public-domain/vonneumann-firstdraft-1945.txt
  hash: placeholder
  ingested: 2026-04-08
  size: 0
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

## Origin: The First Draft of a Report on the EDVAC (1945)

The von Neumann architecture was codified in John von Neumann's "First Draft of a Report on the [[edvac|EDVAC]]," written in the spring of 1945 while he was a consultant at the Moore School of Electrical Engineering at the University of Pennsylvania. The EDVAC was conceived as a successor to [[eniac|ENIAC]], and von Neumann distilled the collective design discussions — involving [[john-mauchly|John Mauchly]] and [[j-presper-eckert|J. Presper Eckert]] among others — into this document.^[vonneumann-firstdraft-1945.txt:7-7]

The First Draft was circulated internally and quickly spread among researchers, shaping the design of early computers across the United States and Britain. The [[ias-machine|IAS machine]] built at Princeton beginning in 1945 was the first computer constructed directly to this specification, and clones of it were built at universities and research laboratories worldwide throughout the late 1940s and 1950s.^[vonneumann-firstdraft-1945.txt:9-9] ^[vonneumann-firstdraft-1945.txt:44-44]

## The Attribution Dispute

Credit for the architecture has been contested. Eckert and Mauchly, along with subsequent historians, argued that many of the ideas in the First Draft arose from collective discussions rather than from von Neumann alone. Nevertheless, the term *von Neumann architecture* persisted because the First Draft was the document that codified and propagated the design to the wider research community.^[vonneumann-firstdraft-1945.txt:9-9]

## Relationship to the Turing Machine

[[alan-turing|Alan Turing]]'s 1936 [[turing-machine]] shares the same conceptual foundation — the idea that an abstract machine with a finite description can compute any computable function. The First Draft translated that mathematical abstraction into a concrete engineering blueprint, making the stored-program computer practically buildable.^[vonneumann-firstdraft-1945.txt:46-46]

## The Von Neumann Bottleneck and Modern Extensions

A performance limitation known as the **von Neumann bottleneck** — the throughput constraint imposed by the single bus connecting the CPU to memory — was identified as early as the 1970s. Modern processor designs mitigate it through caches, multiple memory banks, out-of-order execution, and specialised co-processors, but the fundamental stored-program architecture remains the dominant paradigm. Alternative models including dataflow architectures and neuromorphic computing have been explored but have not displaced the von Neumann machine for general-purpose workloads.^[vonneumann-firstdraft-1945.txt:50-50]