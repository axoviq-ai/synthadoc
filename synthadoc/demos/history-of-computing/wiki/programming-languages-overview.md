---
aliases: []
categories:
- Software, Languages & Operating Systems
confidence: high
created: 2026-04-08
orphan: false
resource: https://ankiweb.net/shared/info/1799825685
sources:
- file: public-domain/wexelblat-history-of-programming-languages-1981.txt
  hash: placeholder
  ingested: 2026-04-08
  size: 0
status: active
tags:
- programming-languages
- history
- compilers
title: Programming Languages Overview
type: concept
updated: '2026-06-30'
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

## Third Generation: LISP and AI (1958–)
While FORTRAN aimed at scientific计算 and COBOL at business record-keeping, LISP emerged from MIT in 1958, devised by John McCarthy for artificial intelligence and symbolic processing. Influenced by Alonzo Church's lambda calculus, LISP prioritized recursion and list processing over numerical computation — a fundamentally different paradigm from mainstream languages of the era.^[wexelblat-history-of-programming-languages-1981.txt:19]^[wexelblat-history-of-programming-languages-1981.txt:19]^[wexelblat-history-of-programming-languages-1981.txt:13,15]^[wexelblat-history-of-programming-languages-1981.txt:25,27]

## Human Factors vs Machine Efficiency
Throughout all generations, language designers have navigated a core tension: prioritizing human readability, expressiveness, and abstraction versus machine efficiency and resource conservation. This dialectic has driven each wave of innovation, from assembly mnemonics to high-level languages like FORTRAN and COBOL, to declarative and functional paradigms exemplified by LISP.^[wexelblat-history-of-programming-languages-1981.txt:13,15]^[wexelblat-history-of-programming-languages-1981.txt:25,27]^[wexelblat-history-of-programming-languages-1981.txt:19]

## Third Generation: LISP and Functional Programming (1958)
In 1958, John McCarthy at MIT developed LISP (LISt Processor), heavily influenced by Alonzo Church's lambda calculus. LISP introduced the concept of treating code as data, enabling self-modifying programs and laying groundwork for artificial intelligence research. McCarthy's work at Dartmouth and MIT built upon theoretical foundations from Church, creating a language that prioritized symbolic manipulation over numerical computation. ^[wexelblat-history-of-programming-languages-1981.txt:19-21]

## Language Pioneers and Institutions
- **John Backus** led the IBM team that developed FORTRAN (Formula Translation), the first successful high-level programming language, transforming scientific computing in 1957. ^[wexelblat-history-of-programming-languages-1981.txt:13-15]
- **John McCarthy** created LISP at MIT, pioneering functional programming paradigms that influenced modern languages like Python and Haskell. ^[wexelblat-history-of-programming-languages-1981.txt:19-21]
- **Grace Hopper** had already demonstrated the compiler concept with A-0 System, establishing the principle of automatic code translation that all subsequent high-level languages would build upon. ^[wexelblat-history-of-programming-languages-1981.txt:15]

These pioneers collectively established the core insight that programming languages should bridge human readability with machine efficiency, enabling abstraction without sacrificing performance.

## Second Generation: FORTRAN and COBOL (1957–1960)

The second generation introduced high-level languages that abstracted machine specifics, significantly improving programmer productivity.

### FORTRAN (1957)
Developed by john-backus at ibm, FORTRAN pioneered optimized compilers for scientific computing. It was the first high-level language to achieve widespread adoption in technical and scientific fields, demonstrating that compiler-generated code could rival hand-written assembly in efficiency.

### LISP (1958)
Created by john-mccarthy at MIT, LISP introduced symbolic computation and automatic memory management through garbage collection. These innovations became foundational to artificial intelligence research and influenced modern functional programming paradigms.

### COBOL (1959)
Developed by CODASYL for the united-states-department-of-defense, COBOL became the standard for business data processing. Its English-like syntax made it accessible to business professionals, establishing the pattern of domain-specific languages.

## Third Generation: LISP and COBOL (Late 1950s)

### LISP (1958)
Developed by john-mccarthy at MIT, LISP (LISt Processing) was designed for symbolic computation and artificial intelligence research. Its key innovations included recursive function definitions, garbage collection, and the use of S-expressions for both code and data. LISP became the dominant language for AI research and influenced later languages like Scheme and Common Lisp. McCarthy received the acm-turing-award in 1971 for his contributions. ^[wexelblat-history-of-programming-languages-1981.txt:19-21]

### COBOL (1959)
Created by a committee convened by the united-states-department-of-defense, COBOL (COmmon Business-Oriented Language) emphasized readability and self-documenting code for business data processing. Its English-like syntax and support for file handling made it widely adopted in government and commercial applications. COBOL's design reflected the needs of large-scale data processing rather than scientific computing. ^[wexelblat-history-of-programming-languages-1981.txt:25-27]

## Impact and Legacy
These early high-level languages demonstrated that the trade-off between human readability and machine efficiency could be managed through compiler technology. [[grace-hopper]]'s earlier work on the A-0 System laid the groundwork for this transition. john-backus led the development of FORTRAN at IBM, which proved that compiled code could approach the efficiency of hand-written assembly. Together, FORTRAN, LISP, and COBOL established the three major paradigms—scientific, symbolic, and business—that shaped the programming landscape for decades. ^[wexelblat-history-of-programming-languages-1981.txt:13-15]

## Third Generation: LISP and Functional Programming (1958–1960)

In 1958, John McCarthy at MIT created LISP (LISt Processor), which became the second major high-level language after FORTRAN and the dominant language for artificial intelligence research. LISP introduced several groundbreaking concepts that remain influential^[wexelblat-history-of-programming-languages-1981.txt:19-21]:

- **List processing**: Data and code both represented as lists, enabling flexible data structures
- **Recursion**: Functions that call themselves, becoming the primary control structure
- **Garbage collection**: Automatic memory management, reclaiming unused memory^[wexelblat-history-of-programming-languages-1981.txt:19-20]

LISP was heavily influenced by Alonzo Church's lambda calculus (1936), providing a theoretical foundation for computation distinct from the von Neumann architecture. The language's symbolic processing capabilities made it ideal for AI research, where it remains significant in modern dialects like Common Lisp and Clojure^[wexelblat-history-of-programming-languages-1981.txt:19,21].

The development of LISP marked a shift toward treating programs as data, a concept that would profoundly influence later languages like Python and JavaScript^[wexelblat-history-of-programming-languages-1981.txt:19].

## Key Pioneers and Milestones

### FORTRAN (1957)
Developed at IBM by John Backus, FORTRAN was the first widely adopted high-level language. Its optimizing compiler was a landmark achievement, demonstrating that automatically generated machine code could rival hand-written assembly in efficiency. FORTRAN established the viability of high-level languages for scientific computing and dominated that domain for decades. ^[wexelblat-history-of-programming-languages-1981.txt:13-15]

### LISP (1958)
Created by John McCarthy at mit, LISP introduced list-based symbolic computation and pioneered automatic garbage collection. Its design drew on Alonzo Church's lambda calculus as its theoretical foundation. LISP became the lingua franca of early [[artificial-intelligence-history|artificial intelligence]] research and remained influential in academic and AI contexts for decades. ^[wexelblat-history-of-programming-languages-1981.txt:19-21]

### COBOL (1959)
Designed under the direction of [[grace-hopper|Grace Hopper]], COBOL was built for business-oriented data processing. Its English-like syntax was deliberately crafted to make programs readable by non-technical managers, reflecting Hopper's lifelong conviction that programming should be accessible to domain experts rather than restricted to specialists. ^[wexelblat-history-of-programming-languages-1981.txt:25-27]

## The Readability–Efficiency Tension

The history of programming languages can be framed as a persistent tension between two goals: human readability and machine efficiency. Early high-level languages like FORTRAN, LISP, and COBOL each resolved this tension differently — FORTRAN prioritized runtime performance for scientific workloads, LISP favored expressive power for symbolic reasoning, and COBOL emphasized clarity for business stakeholders. This trade-off continues to shape language design today. ^[wexelblat-history-of-programming-languages-1981.txt:3-3]

## Third Generation: LISP and the Rise of Symbolic Computation (1958)
John McCarthy developed LISP at MIT in 1958 as a language for artificial intelligence research. Its design centered on symbolic processing, recursion, and the revolutionary idea of 'code-as-data' — enabling programs to manipulate their own structure. LISP introduced automatic memory management via garbage-collection, a foundational innovation later adopted across many languages. McCarthy’s work built on theoretical foundations laid by [[alan-turing]] and alonzo-church, and was supported by early funding from DARPA and institutions like MIT and Stanford.^[19-20]

## Design Trade-offs and Enduring Innovations
Beyond syntax and domain focus, these early high-level languages embodied competing priorities: FORTRAN prioritized numerical efficiency and hardware mapping; COBOL emphasized business-domain readability and portability across ibm and other mainframes; LISP privileged abstraction, extensibility, and metaprogramming. Collectively, they established core concepts still central today — compilers (pioneered by [[grace-hopper]]’s A-0 and refined by John Backus’s FORTRAN team at ibm), runtime memory management, and the separation of problem specification from machine execution.^[13-15,19-20,25-27]

## Third Generation: LISP and Symbolic Computation (1958)

While FORTRAN was optimising numerical computation, john-mccarthy at mit developed LISP (List Processing) in 1958, introducing a fundamentally different paradigm. LISP was grounded in alonzo-church's lambda calculus and was designed for symbolic rather than numeric computation. ^[wexelblat-history-of-programming-languages-1981.txt:19-21] It became the dominant language of [[artificial-intelligence-history|artificial intelligence]] research for decades, introducing concepts such as recursion, garbage collection, and code-as-data that continue to influence language design today. ^[wexelblat-history-of-programming-languages-1981.txt:19-21]

## COBOL and Business Data Processing (1959–1960)

Building on the FLOW-MATIC language developed by [[grace-hopper]], the CODASYL committee (with Hopper's influence) created COBOL (Common Business-Oriented Language) in 1959–1960. ^[wexelblat-history-of-programming-languages-1981.txt:25] COBOL's English-like syntax was deliberately designed to be readable by non-technical business managers, and it became the standard for commercial data processing — a role it maintained in mainframes for decades. ^[wexelblat-history-of-programming-languages-1981.txt:27]

## Key Figures in Early Language Design

- **John Backus** led the ibm team that created FORTRAN, pioneering the idea that compilers could optimise code to rival hand-written assembly. ^[wexelblat-history-of-programming-languages-1981.txt:15]
- **John McCarthy** created LISP at mit, linking programming language theory to mathematical logic via the lambda calculus. ^[wexelblat-history-of-programming-languages-1981.txt:19]
- **Grace Hopper** championed the concept of human-readable programming and drove the development of COBOL. ^[wexelblat-history-of-programming-languages-1981.txt:25]

## Key Pioneers of High-Level Languages

The development of the first widely used high-level languages was driven by distinct figures who each shaped the direction of programming:

- **John Backus** led the IBM team that created **FORTRAN** (1957), the first widely adopted high-level language, designed to make scientific computing practical for working scientists and engineers who were not assembly specialists.^[FILENAME:13-15]
- **John McCarthy** created **LISP** (1958) at MIT, introducing recursive function notation, garbage collection, and the homoiconic S-expression syntax that would shape symbolic computing and [[artificial-intelligence-history|artificial intelligence]] research for decades.^[FILENAME:19-21]
- **[[grace-hopper|Grace Hopper]]** was the driving force behind **COBOL** (1959), championing a human-readable, English-like syntax aimed at business data processing, and convening the CODASYL committee that standardised it across vendors.^[FILENAME:25-27]

## The Readability–Efficiency Tradeoff

Each of these foundational languages embodied a different point on the readability-versus-efficiency spectrum. FORTRAN prioritised generating near-assembly performance while freeing programmers from manual register allocation.^[FILENAME:15] LISP prioritised expressive power and symbolic manipulation over execution speed.^[FILENAME:19-21] COBOL prioritised clarity for non-specialists writing record-keeping and financial applications.^[FILENAME:27] The fact that all three coexisted — rather than one superseding the others — reflects the reality that different problem domains demand different language design points.

## FORTRAN — readable notation meets efficient compilation

john-backus led the ibm team that produced FORTRAN (Formula Translation) in 1957, introducing a high-level language whose arithmetic notation resembled mathematical expressions while still compiling to efficient machine code. ^[wexelblat-history-of-programming-languages-1981.txt:13-13] Backus argued that programmers should be freed from writing in assembly, and that compilers could rival hand-coded machine code in performance — a claim that was initially met with scepticism but ultimately validated. ^[wexelblat-history-of-programming-languages-1981.txt:13-15] FORTRAN's success established that abstraction and efficiency were not mutually exclusive, and it set the template for decades of compiled high-level languages. ^[wexelblat-history-of-programming-languages-1981.txt:15-15]

## LISP — symbolic computation and garbage collection

In 1958, john-mccarthy at mit designed LISP (List Processing), drawing on the lambda calculus formalism of alonzo-church. ^[wexelblat-history-of-programming-languages-1981.txt:19-19] LISP introduced several innovations that remain influential: a homoiconic representation in which code and data share the same list structure, first-class functions, recursive function definitions as the primary control mechanism, and automatic memory management through garbage collection. ^[wexelblat-history-of-programming-languages-1981.txt:19-19] These features made LISP the dominant language for artificial intelligence research throughout the 1960s and 1970s, and its ideas about symbolic computation and dynamic memory management continue to shape modern functional and dynamic languages. ^[wexelblat-history-of-programming-languages-1981.txt:19-21]

## COBOL — business data processing

[[grace-hopper]] played a central role in the design of COBOL (Common Business-Oriented Language, 1959–1960), championing the idea that programs should resemble English so that business domain experts — not just mathematicians — could read and write them. ^[wexelblat-history-of-programming-languages-1981.txt:25-27] Developed under the guidance of the united-states-department-of-defense, COBOL emphasised data description, fixed-format records, and portability across hardware vendors. ^[wexelblat-history-of-programming-languages-1981.txt:25-27] It became the dominant language for commercial data processing for decades. ^[wexelblat-history-of-programming-languages-1981.txt:27-27]

## The Balancing Theme

The evolution of programming languages can be read as an ongoing negotiation between human cognitive needs (readability, abstraction, expressiveness) and machine execution constraints (speed, memory footprint, predictability). ^[wexelblat-history-of-programming-languages-1981.txt:3-3] FORTRAN optimised for execution efficiency, LISP for expressive symbolic reasoning, and COBOL for domain readability. Each generation of languages has revisited this tradeoff, and the tension remains central to language design today.

## LISP and Symbolic Computation (1958)

While FORTRAN targeted scientific computation, john-mccarthy at mit took a fundamentally different approach with LISP in 1958, designing the language around symbolic rather than numeric computation. LISP pioneered several ideas that became central to computer science: first-class functions, linked lists as a primary data structure, and automatic memory management through garbage collection. ^[wexelblat-history-of-programming-languages-1981.txt:19-19]

LISP's theoretical roots trace to the lambda-calculus developed by alonzo-church, which gave the language its name and its foundational model of computation via function application. McCarthy, working in the context of early artificial-intelligence research at MIT, needed a language suited to manipulating symbols, expressions, and recursive structures rather than arrays of numbers. ^[wexelblat-history-of-programming-languages-1981.txt:19-21]

The introduction of garbage collection was not merely a convenience — it reflected the belief that programmers should be freed from manual memory bookkeeping to focus on the logic of symbolic reasoning. This made LISP especially well suited to the exploratory, research-oriented style of AI work at MIT and later stanford, where it remained a dominant language for decades. ^[wexelblat-history-of-programming-languages-1981.txt:19-21]

LISP and fortran together illustrate the early divergence of language design: FORTRAN optimised for raw numerical performance and tight machine efficiency, while LISP prioritised expressiveness and abstraction for a class of problems where performance was secondary to representational power. This tension between human readability and machine efficiency, already visible in the shift from assembly-language to high-level notation, continued to shape language design in subsequent generations. ^[wexelblat-history-of-programming-languages-1981.txt:3-3]

## COBOL and Business Data Processing (1959–1960)

In parallel with LISP, [[grace-hopper]] and a committee she chaired championed COBOL (Common Business-Oriented Language), which became the dominant language for business data processing. See [[grace-hopper]] for details on her broader contributions to programming language design. ^[wexelblat-history-of-programming-languages-1981.txt:25-27]

## LISP and Symbolic Computation (1958)

While FORTRAN targeted numerical scientific computing, john-mccarthy at mit developed LISP in 1958, the second-oldest high-level language still in use today. LISP was grounded in the lambda calculus formulated by Alonzo Church, making it fundamentally suited to symbolic computation and artificial intelligence research. ^[wexelblat-history-of-programming-languages-1981.txt:19-21] Its introduction demonstrated that high-level languages could serve domains far beyond numerical calculation, and it pioneered concepts such as recursion, garbage collection, and code-as-data that remain influential in language design. ^[wexelblat-history-of-programming-languages-1981.txt:19]

## The Core Tension in Language Design

A persistent theme running through the evolution of programming languages is the tension between human readability and expressiveness on one hand, and machine efficiency and precision on the other. ^[wexelblat-history-of-programming-languages-1981.txt:3] From raw machine code and assembly languages, through the optimizing compiler of fortran, to the symbolic flexibility of LISP and the English-like syntax of cobol, each generation represented a different point on this spectrum. [[grace-hopper]]'s vision of programs written in human-readable language ^[wexelblat-history-of-programming-languages-1981.txt:25-27] and john-backus's demonstration that high-level abstractions could match hand-tuned machine code ^[wexelblat-history-of-programming-languages-1981.txt:15] each pushed the boundary in opposite directions — toward human expressiveness and toward machine performance, respectively — yet both proved foundational to modern computing.

## Symbolic Computation and LISP (1958)

While FORTRAN was optimizing for numerical scientific work, john-mccarthy at MIT took a fundamentally different approach. In 1958, he designed LISP (List Processing), the second-oldest high-level programming language still in use today. LISP introduced several ideas that would shape the entire field of computing: ^[wexelblat-history-of-programming-languages-1981.txt:19-19]

- **Symbolic rather than numeric computation**: where FORTRAN treated programs as loops over arrays of numbers, LISP operated on symbolic expressions — lists, trees, and recursive structures — making it the native language of artificial intelligence research. ^[wexelblat-history-of-programming-languages-1981.txt:19-21]
- **Garbage collection**: LISP was the first language to automatically reclaim unused memory, freeing programmers from manual memory management. ^[wexelblat-history-of-programming-languages-1981.txt:19-19]
- **Code as data (homoiconicity)**: LISP programs were written in the same S-expression syntax as the data they manipulated, blurring the line between program and input. ^[wexelblat-history-of-programming-languages-1981.txt:19-19]

McCarthy's work demonstrated that high-level languages were not solely about making numerical computing more accessible — they could open entirely new computational paradigms that machine code made impractical to explore. ^[wexelblat-history-of-programming-languages-1981.txt:19-21]

## The Recurring Tension: Readability vs. Efficiency

The history of early programming languages reflects a constant negotiation between human expressiveness and machine performance. [[grace-hopper]], who championed human-readable code through FLOW-MATIC and the committee that produced COBOL, pushed the industry toward natural-language syntax. John Backus, by contrast, accepted that FORTRAN programs would look like mathematics but justified the trade-off with the compiler's ability to generate machine code nearly as efficient as hand-written assembly. Every subsequent language — from C to Python to modern quantum SDKs — has had to pick a new point along this same spectrum. ^[wexelblat-history-of-programming-languages-1981.txt:3-3] ^[wexelblat-history-of-programming-languages-1981.txt:13-15] ^[wexelblat-history-of-programming-languages-1981.txt:25-27]

## Key Figures in Early Language Development

The development of early high-level languages was driven by several pioneering figures whose work shaped the trajectory of programming language design.

- **John Backus** led the ibm team that created FORTRAN (Formula Translation) in 1957, the first widely adopted high-level programming language. Backus also later contributed to the formal description of programming languages through Backus-Naur Form (BNF). ^[FILENAME:13-13]
- **John McCarthy** created LISP (List Processing) at mit in 1958, introducing foundational concepts such as recursion, garbage collection, and symbolic computation that influenced decades of language design. ^[FILENAME:19-19]
- **Alonzo Church** developed the lambda calculus, a formal system for expressing computation that became a theoretical foundation for functional programming languages. ^[FILENAME:19-19]
- **Grace Hopper** championed the development of FLOW-MATIC in the 1950s, a business-oriented English-like language that directly influenced the design of COBOL. Her vision of human-readable programming was initially dismissed by contemporaries but ultimately transformed software development. ^[FILENAME:25-25]

## The Readability–Efficiency Tension

Throughout the history of programming languages, a central tension has existed between human readability and machine efficiency. ^[FILENAME:3-3] Early machine code and assembly languages prioritized direct hardware control but were difficult to write and maintain. ^[FILENAME:7-9] High-level languages like FORTRAN, LISP, and COBOL introduced abstractions that made programming more accessible, but at the cost of less direct control over hardware. ^[FILENAME:3-3] This trade-off continues to shape language design, with each generation of languages attempting to find new balances between expressiveness and performance. ^[FILENAME:3-3] The work of figures like Backus, McCarthy, Church, and [[grace-hopper]] illustrates different points on this spectrum — from FORTRAN's focus on efficient numerical computation, ^[FILENAME:15-15] to LISP's emphasis on symbolic expressiveness, ^[FILENAME:21-21] to COBOL's readability for business applications. ^[FILENAME:27-27]

## Web and Scripting Languages (1995–Present)

JavaScript, created by Brendan Eich at Netscape in 1995, became the dominant language for client-side web interactivity.^[1799825685:1-1] It was standardized as ecmascript (ECMA-262), with Node.js extending its runtime to server-side development. Alongside html and css, JavaScript forms the core triad of front-end web development. Its event-driven, prototype-based design and ubiquity in browsers made it one of the most widely deployed programming languages in history.