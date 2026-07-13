---
aliases: []
categories:
- Recently Added
confidence: medium
created: '2026-07-13T01:38:24'
lint_warnings:
- claim: binary floating-point arithmetic using mechanical relays
 concern: The Z1 used purely mechanical components (metal plates and pins), not mechanical
 relays. It was a mechanical binary calculator, not an electromechanical one.
- claim: any computable function could be expressed in its instruction set using conditional
 loops created by looping the tape
 concern: Rojas's 1998 proof of the Z3's Turing completeness relied on a theoretical
 reconstruction with certain missing operations patched in, not on the Z3's original
 instruction set as built. The Z3 lacked a conditional branch instruction, so unconditional
 looping of the tape does not constitute true conditional branching.
orphan: false
sources:
- file: C:\Users\ladmin\wikis\history-of-computing\raw_sources\konrad-zuse-z3-computer.md
 hash: 66cb25d17f16c4ab8fc4703cf2827bbb1db26684859b68428c1a5fed2f9815e1
 ingested: '2026-07-13T01:38:24'
 size: 2783
status: active
tags:
- computing history
- programmable computer
- binary floating-point
- relay logic
- Turing completeness
- high-level programming language
- wartime computing
- civil engineering
- German engineering
- stored-program
title: Konrad Zuse
type: person
updated: '2026-07-12'
---

# Konrad Zuse

Konrad Zuse (1910–1995) was a German civil engineer and computer pioneer who, largely in isolation from the Anglo-American computing efforts of the 1940s, designed and built a series of computing machines in his parents' living room in Berlin. ^[konrad-zuse-z3-computer.md:5-7] His work demonstrates that the development of the digital computer was not solely an Anglo-American achievement — it emerged independently on both sides of the Atlantic under wartime pressure and without cross-pollination of ideas. ^[konrad-zuse-z3-computer.md:55-59]

## The Z1 (1938)

Zuse's first machine, the Z1, was a mechanical binary calculator built almost entirely from sheet metal cut by hand. It was unreliable due to manufacturing tolerances but demonstrated the core concept: binary floating-point arithmetic using mechanical relays. The Z1 was destroyed in the Allied bombing of Berlin in 1943. ^[konrad-zuse-z3-computer.md:11-14]

## The Z3 (1941)

The Z3, completed in May 1941, is recognised by most historians as the world's first working programmable, fully automatic digital computer. ^[konrad-zuse-z3-computer.md:18-19] Key specifications:

- **Technology:** 2,600 telephone relay switches
- **Word length:** 22-bit floating-point
- **Clock speed:** approximately 5–10 Hz (one multiplication per 3 seconds)
- **Programming:** punched film (35 mm cinema strip) — sequences of operations encoded as holes in the tape
- **Memory:** 64 words (limited by relay count) ^[konrad-zuse-z3-computer.md:21-26]

Unlike colossus (1943) or eniac (1945), the Z3 was a general-purpose stored-program machine in principle, though its tape-based programming was more limited than the stored memory designs described in [[von-neumann-architecture]]. ^[konrad-zuse-z3-computer.md:28-30]

## Turing Completeness

In 1998, Raúl Rojas demonstrated that the Z3 was Turing-complete — any computable function could be expressed in its instruction set using conditional loops created by looping the tape. Zuse himself was unaware of [[alan-turing]]'s work and arrived at similar theoretical foundations independently. ^[konrad-zuse-z3-computer.md:34-37]

## Commercial Success: The Z4

After World War II, Zuse built the Z4 (1950), which was leased to the ETH Zürich — making it the first commercially used computer in continental Europe. The Z4 ran reliably for years, processing structural engineering calculations. ^[konrad-zuse-z3-computer.md:41-43]

## Plankalkül: The First High-Level Programming Language

Between 1942 and 1945, Zuse designed **Plankalkül** (Plan Calculus), a high-level programming language with variables, subroutines, and data structures. It was not published until 1972 and not fully implemented until 2000 — decades after FORTRAN, COBOL, and LISP. Nonetheless, Plankalkül is considered the first design of a high-level programming language. ^[konrad-zuse-z3-computer.md:47-51]

## Legacy

Zuse founded Zuse KG in 1949, one of the first computer companies in Europe, and continued building relay and transistor-based machines through the 1950s and 1960s. ^[konrad-zuse-z3-computer.md:55-56]

## See Also

- [[alan-turing]] — contemporaneous theoretical work on computation
- [[von-neumann-architecture]] — the stored-program model that followed
- [[artificial-intelligence-history]] — Zuse is mentioned among computing pioneers
- [[grace-hopper]] — later pioneer of high-level programming languages

## Z3 Technical Specifications

The Z3, completed in May 1941, is recognised by most historians as the world's first working programmable, fully automatic digital computer. ^[konrad-zuse-z3-computer.md:18-19] Key specifications included:

- **Technology:** 2,600 telephone relay switches ^[konrad-zuse-z3-computer.md:21-21]
- **Word length:** 22-bit floating-point ^[konrad-zuse-z3-computer.md:22-22]

- **Clock speed:** approximately 5–10 Hz (roughly one multiplication every 3 seconds) ^[konrad-zuse-z3-computer.md:23-23]

- **Programming:** punched 35 mm cinema film strip, with sequences of operations encoded as holes in the tape ^[konrad-zuse-z3-computer.md:24-25]

- **Memory:** 64 words (limited by available relay count) ^[konrad-zuse-z3-computer.md:26-26]

Unlike [[colossus]] (1943) or [[eniac]] (1945), the Z3 was a general-purpose stored-program machine in principle, though its tape-based programming was more constrained than the stored-memory designs that followed. ^[konrad-zuse-z3-computer.md:28-30]

## Turing Completeness (1998)

In 1998, computer scientist Raúl Rojas demonstrated that the Z3 was Turing-complete — any computable function could be expressed in its instruction set using conditional loops achieved by looping the punched tape. ^[konrad-zuse-z3-computer.md:34-35] Zuse himself was unaware of [[alan-turing]]'s theoretical work and arrived at equivalent computational foundations independently. ^[konrad-zuse-z3-computer.md:36-37]

## The Z4 at ETH Zürich

After World War II, Zuse completed the Z4 in 1950, which was leased to the ETH Zürich — making it the first commercially operated computer in continental Europe. ^[konrad-zuse-z3-computer.md:41-42] The Z4 ran reliably for years, primarily processing structural engineering calculations. ^[konrad-zuse-z3-computer.md:42-43]

## Plankalkül

Between 1942 and 1945, Zuse designed **Plankalkül** (Plan Calculus), a high-level programming language supporting variables, subroutines, and structured data types. ^[konrad-zuse-z3-computer.md:47-48] Although not published until 1972 and not fully implemented until 2000 — decades after FORTRAN, COBOL, and LISP — Plankalkül is considered the first design of a high-level programming language. ^[konrad-zuse-z3-computer.md:48-51]

## Zuse KG

Zuse founded Zuse KG in 1949, one of the earliest computer companies in Europe, and continued building relay- and transistor-based machines through the 1950s and 1960s. ^[konrad-zuse-z3-computer.md:55-56]