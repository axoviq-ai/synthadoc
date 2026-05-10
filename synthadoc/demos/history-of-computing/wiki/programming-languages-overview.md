---
title: Programming Languages Overview
tags: [programming-languages, history, compilers]
status: active
confidence: high
created: 2026-04-08
sources:
  - file: public-domain/wexelblat-history-of-programming-languages-1981.txt
    hash: placeholder
    size: 0
    ingested: 2026-04-08
aliases: []
---

# Programming Languages Overview

Programming languages are formal notations for expressing computation. Their history reflects a constant tension between expressiveness and efficiency, between human readability and machine performance.

## First Generation: Machine Code and Assembly (1940s–1950s)

The earliest computers were programmed in binary machine code tied directly to the [[von-neumann-architecture]] instruction set. Assembly languages added symbolic names for instructions, but programmers still mapped every operation manually.

## Second Generation: FORTRAN and COBOL (1957–1960)

John Backus at IBM developed FORTRAN (1957), the first widely used high-level language, targeting scientific computation. COBOL (1959), shaped by [[grace-hopper|Grace Hopper]], targeted business data processing and introduced English-like syntax.

## Third Generation: Structured Programming (1960s–1970s)

Edsger Dijkstra's 1968 letter "Go To Statement Considered Harmful" catalysed structured programming. C (1972, Bell Labs — see [[unix-history]]) and Pascal became the canonical languages of this era. C's portability was inseparable from the spread of [[unix-history]] itself.

## Fourth Generation: Object-Oriented and Functional (1980s–1990s)

Simula (1967) introduced objects; Smalltalk made them central. C++ (1985) brought objects to the systems level. Haskell (1990) advanced purely functional programming. Java (1995) prioritised portability via the JVM.

## Modern Era: Scripting, Safety, and Concurrency (2000s–present)

Python's simplicity drove adoption in data science and [[internet-origins]] web services. Rust (2015) introduced memory safety without a garbage collector. Go (2009) targeted the concurrency demands of cloud-scale [[internet-origins]] infrastructure.

## Computability Foundations

All programming languages are ultimately rooted in the theory of computation formalised by [[alan-turing]]. A language is Turing-complete if it can express any computable function — nearly every general-purpose language meets this bar.
