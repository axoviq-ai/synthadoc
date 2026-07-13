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
updated: '2026-07-12'
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
While FORTRAN aimed at scientific计算 and COBOL at business record-keeping, LISP emerged from MIT in 1958, devised by John McCarthy for artificial intelligence and symbolic processing. Influenced by Alonzo Church's lambda calculus, LISP prioritized recursion and list processing over numerical computation — a fundamentally different paradigm from mainstream languages of the era.

## Human Factors vs Machine Efficiency
Throughout all generations, language designers have navigated a core tension: prioritizing human readability, expressiveness, and abstraction versus machine efficiency and resource conservation. This dialectic has driven each wave of innovation, from assembly mnemonics to high-level languages like FORTRAN and COBOL, to declarative and functional paradigms exemplified by LISP.

## Third Generation: LISP and Functional Programming (1958)
In 1958, John McCarthy at MIT developed LISP (LISt Processor), heavily influenced by Alonzo Church's lambda calculus. LISP introduced the concept of treating code as data, enabling self-modifying programs and laying groundwork for artificial intelligence research. McCarthy's work at Dartmouth and MIT built upon theoretical foundations from Church, creating a language that prioritized symbolic manipulation over numerical computation.

## Language Pioneers and Institutions
- **John Backus** led the IBM team that developed FORTRAN (Formula Translation), the first successful high-level programming language, transforming scientific computing in 1957.
- **John McCarthy** created LISP at MIT, pioneering functional programming paradigms that influenced modern languages like Python and Haskell.
- **Grace Hopper** had already demonstrated the compiler concept with A-0 System, establishing the principle of automatic code translation that all subsequent high-level languages would build upon.

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
Developed by john-mccarthy at MIT, LISP (LISt Processing) was designed for symbolic computation and artificial intelligence research. Its key innovations included recursive function definitions, garbage collection, and the use of S-expressions for both code and data. LISP became the dominant language for AI research and influenced later languages like Scheme and Common Lisp. McCarthy received the acm-turing-award in 1971 for his contributions.

### COBOL (1959)
Created by a committee convened by the united-states-department-of-defense, COBOL (COmmon Business-Oriented Language) emphasized readability and self-documenting code for business data processing. Its English-like syntax and support for file handling made it widely adopted in government and commercial applications. COBOL's design reflected the needs of large-scale data processing rather than scientific computing.

## Impact and Legacy
These early high-level languages demonstrated that the trade-off between human readability and machine efficiency could be managed through compiler technology. [[grace-hopper]]'s earlier work on the A-0 System laid the groundwork for this transition. john-backus led the development of FORTRAN at IBM, which proved that compiled code could approach the efficiency of hand-written assembly. Together, FORTRAN, LISP, and COBOL established the three major paradigms—scientific, symbolic, and business—that shaped the programming landscape for decades.

## Third Generation: LISP and Functional Programming (1958–1960)

In 1958, John McCarthy at MIT created LISP (LISt Processor), which became the second major high-level language after FORTRAN and the dominant language for artificial intelligence research. LISP introduced several groundbreaking concepts that remain influential:

- **List processing**: Data and code both represented as lists, enabling flexible data structures
- **Recursion**: Functions that call themselves, becoming the primary control structure
- **Garbage collection**: Automatic memory management, reclaiming unused memory

LISP was heavily influenced by Alonzo Church's lambda calculus (1936), providing a theoretical foundation for computation distinct from the von Neumann architecture. The language's symbolic processing capabilities made it ideal for AI research, where it remains significant in modern dialects like Common Lisp and Clojure.

The development of LISP marked a shift toward treating programs as data, a concept that would profoundly influence later languages like Python and JavaScript.

## Key Pioneers and Milestones

### FORTRAN (1957)
Developed at IBM by John Backus, FORTRAN was the first widely adopted high-level language. Its optimizing compiler was a landmark achievement, demonstrating that automatically generated machine code could rival hand-written assembly in efficiency. FORTRAN established the viability of high-level languages for scientific computing and dominated that domain for decades.

### LISP (1958)
Created by John McCarthy at mit, LISP introduced list-based symbolic computation and pioneered automatic garbage collection. Its design drew on Alonzo Church's lambda calculus as its theoretical foundation. LISP became the lingua franca of early [[artificial-intelligence-history|artificial intelligence]] research and remained influential in academic and AI contexts for decades.

### COBOL (1959)
Designed under the direction of [[grace-hopper|Grace Hopper]], COBOL was built for business-oriented data processing. Its English-like syntax was deliberately crafted to make programs readable by non-technical managers, reflecting Hopper's lifelong conviction that programming should be accessible to domain experts rather than restricted to specialists.

## The Readability–Efficiency Tension

The history of programming languages can be framed as a persistent tension between two goals: human readability and machine efficiency. Early high-level languages like FORTRAN, LISP, and COBOL each resolved this tension differently — FORTRAN prioritized runtime performance for scientific workloads, LISP favored expressive power for symbolic reasoning, and COBOL emphasized clarity for business stakeholders. This trade-off continues to shape language design today.

## Third Generation: LISP and the Rise of Symbolic Computation (1958)
John McCarthy developed LISP at MIT in 1958 as a language for artificial intelligence research. Its design centered on symbolic processing, recursion, and the revolutionary idea of 'code-as-data' — enabling programs to manipulate their own structure. LISP introduced automatic memory management via garbage-collection, a foundational innovation later adopted across many languages. McCarthy’s work built on theoretical foundations laid by [[alan-turing]] and alonzo-church, and was supported by early funding from DARPA and institutions like MIT and Stanford.

## Design Trade-offs and Enduring Innovations
Beyond syntax and domain focus, these early high-level languages embodied competing priorities: FORTRAN prioritized numerical efficiency and hardware mapping; COBOL emphasized business-domain readability and portability across ibm and other mainframes; LISP privileged abstraction, extensibility, and metaprogramming. Collectively, they established core concepts still central today — compilers (pioneered by [[grace-hopper]]’s A-0 and refined by John Backus’s FORTRAN team at ibm), runtime memory management, and the separation of problem specification from machine execution.

## Third Generation: LISP and Symbolic Computation (1958)

While FORTRAN was optimising numerical computation, john-mccarthy at mit developed LISP (List Processing) in 1958, introducing a fundamentally different paradigm. LISP was grounded in alonzo-church's lambda calculus and was designed for symbolic rather than numeric computation. It became the dominant language of [[artificial-intelligence-history|artificial intelligence]] research for decades, introducing concepts such as recursion, garbage collection, and code-as-data that continue to influence language design today.

## COBOL and Business Data Processing (1959–1960)

Building on the FLOW-MATIC language developed by [[grace-hopper]], the CODASYL committee (with Hopper's influence) created COBOL (Common Business-Oriented Language) in 1959–1960. COBOL's English-like syntax was deliberately designed to be readable by non-technical business managers, and it became the standard for commercial data processing — a role it maintained in mainframes for decades.

## Key Figures in Early Language Design

- **John Backus** led the ibm team that created FORTRAN, pioneering the idea that compilers could optimise code to rival hand-written assembly.
- **John McCarthy** created LISP at mit, linking programming language theory to mathematical logic via the lambda calculus.
- **Grace Hopper** championed the concept of human-readable programming and drove the development of COBOL.

## Key Pioneers of High-Level Languages

The development of the first widely used high-level languages was driven by distinct figures who each shaped the direction of programming:

- **John Backus** led the IBM team that created **FORTRAN** (1957), the first widely adopted high-level language, designed to make scientific computing practical for working scientists and engineers who were not assembly specialists.
- **John McCarthy** created **LISP** (1958) at MIT, introducing recursive function notation, garbage collection, and the homoiconic S-expression syntax that would shape symbolic computing and [[artificial-intelligence-history|artificial intelligence]] research for decades.
- **[[grace-hopper|Grace Hopper]]** was the driving force behind **COBOL** (1959), championing a human-readable, English-like syntax aimed at business data processing, and convening the CODASYL committee that standardised it across vendors.

## The Readability–Efficiency Tradeoff

Each of these foundational languages embodied a different point on the readability-versus-efficiency spectrum. FORTRAN prioritised generating near-assembly performance while freeing programmers from manual register allocation. LISP prioritised expressive power and symbolic manipulation over execution speed. COBOL prioritised clarity for non-specialists writing record-keeping and financial applications. The fact that all three coexisted — rather than one superseding the others — reflects the reality that different problem domains demand different language design points.

## FORTRAN — readable notation meets efficient compilation

john-backus led the ibm team that produced FORTRAN (Formula Translation) in 1957, introducing a high-level language whose arithmetic notation resembled mathematical expressions while still compiling to efficient machine code. Backus argued that programmers should be freed from writing in assembly, and that compilers could rival hand-coded machine code in performance — a claim that was initially met with scepticism but ultimately validated. FORTRAN's success established that abstraction and efficiency were not mutually exclusive, and it set the template for decades of compiled high-level languages.

## LISP — symbolic computation and garbage collection

In 1958, john-mccarthy at mit designed LISP (List Processing), drawing on the lambda calculus formalism of alonzo-church. LISP introduced several innovations that remain influential: a homoiconic representation in which code and data share the same list structure, first-class functions, recursive function definitions as the primary control mechanism, and automatic memory management through garbage collection. These features made LISP the dominant language for artificial intelligence research throughout the 1960s and 1970s, and its ideas about symbolic computation and dynamic memory management continue to shape modern functional and dynamic languages.

## COBOL — business data processing

[[grace-hopper]] played a central role in the design of COBOL (Common Business-Oriented Language, 1959–1960), championing the idea that programs should resemble English so that business domain experts — not just mathematicians — could read and write them. Developed under the guidance of the united-states-department-of-defense, COBOL emphasised data description, fixed-format records, and portability across hardware vendors. It became the dominant language for commercial data processing for decades.

## The Balancing Theme

The evolution of programming languages can be read as an ongoing negotiation between human cognitive needs (readability, abstraction, expressiveness) and machine execution constraints (speed, memory footprint, predictability). FORTRAN optimised for execution efficiency, LISP for expressive symbolic reasoning, and COBOL for domain readability. Each generation of languages has revisited this tradeoff, and the tension remains central to language design today.

## LISP and Symbolic Computation (1958)

While FORTRAN targeted scientific computation, john-mccarthy at mit took a fundamentally different approach with LISP in 1958, designing the language around symbolic rather than numeric computation. LISP pioneered several ideas that became central to computer science: first-class functions, linked lists as a primary data structure, and automatic memory management through garbage collection.

LISP's theoretical roots trace to the lambda-calculus developed by alonzo-church, which gave the language its name and its foundational model of computation via function application. McCarthy, working in the context of early artificial-intelligence research at MIT, needed a language suited to manipulating symbols, expressions, and recursive structures rather than arrays of numbers.

The introduction of garbage collection was not merely a convenience — it reflected the belief that programmers should be freed from manual memory bookkeeping to focus on the logic of symbolic reasoning. This made LISP especially well suited to the exploratory, research-oriented style of AI work at MIT and later stanford, where it remained a dominant language for decades.

LISP and fortran together illustrate the early divergence of language design: FORTRAN optimised for raw numerical performance and tight machine efficiency, while LISP prioritised expressiveness and abstraction for a class of problems where performance was secondary to representational power. This tension between human readability and machine efficiency, already visible in the shift from assembly-language to high-level notation, continued to shape language design in subsequent generations.

## COBOL and Business Data Processing (1959–1960)

In parallel with LISP, [[grace-hopper]] and a committee she chaired championed COBOL (Common Business-Oriented Language), which became the dominant language for business data processing. See [[grace-hopper]] for details on her broader contributions to programming language design.

## LISP and Symbolic Computation (1958)

While FORTRAN targeted numerical scientific computing, john-mccarthy at mit developed LISP in 1958, the second-oldest high-level language still in use today. LISP was grounded in the lambda calculus formulated by Alonzo Church, making it fundamentally suited to symbolic computation and artificial intelligence research. Its introduction demonstrated that high-level languages could serve domains far beyond numerical calculation, and it pioneered concepts such as recursion, garbage collection, and code-as-data that remain influential in language design.

## The Core Tension in Language Design

A persistent theme running through the evolution of programming languages is the tension between human readability and expressiveness on one hand, and machine efficiency and precision on the other. From raw machine code and assembly languages, through the optimizing compiler of fortran, to the symbolic flexibility of LISP and the English-like syntax of cobol, each generation represented a different point on this spectrum. [[grace-hopper]]'s vision of programs written in human-readable language and john-backus's demonstration that high-level abstractions could match hand-tuned machine code each pushed the boundary in opposite directions — toward human expressiveness and toward machine performance, respectively — yet both proved foundational to modern computing.

## Symbolic Computation and LISP (1958)

While FORTRAN was optimizing for numerical scientific work, john-mccarthy at MIT took a fundamentally different approach. In 1958, he designed LISP (List Processing), the second-oldest high-level programming language still in use today. LISP introduced several ideas that would shape the entire field of computing:

- **Symbolic rather than numeric computation**: where FORTRAN treated programs as loops over arrays of numbers, LISP operated on symbolic expressions — lists, trees, and recursive structures — making it the native language of artificial intelligence research.
- **Garbage collection**: LISP was the first language to automatically reclaim unused memory, freeing programmers from manual memory management.
- **Code as data (homoiconicity)**: LISP programs were written in the same S-expression syntax as the data they manipulated, blurring the line between program and input.

McCarthy's work demonstrated that high-level languages were not solely about making numerical computing more accessible — they could open entirely new computational paradigms that machine code made impractical to explore.

## The Recurring Tension: Readability vs. Efficiency

The history of early programming languages reflects a constant negotiation between human expressiveness and machine performance. [[grace-hopper]], who championed human-readable code through FLOW-MATIC and the committee that produced COBOL, pushed the industry toward natural-language syntax. John Backus, by contrast, accepted that FORTRAN programs would look like mathematics but justified the trade-off with the compiler's ability to generate machine code nearly as efficient as hand-written assembly. Every subsequent language — from C to Python to modern quantum SDKs — has had to pick a new point along this same spectrum.

## Key Figures in Early Language Development

The development of early high-level languages was driven by several pioneering figures whose work shaped the trajectory of programming language design.

- **John Backus** led the ibm team that created FORTRAN (Formula Translation) in 1957, the first widely adopted high-level programming language. Backus also later contributed to the formal description of programming languages through Backus-Naur Form (BNF).
- **John McCarthy** created LISP (List Processing) at mit in 1958, introducing foundational concepts such as recursion, garbage collection, and symbolic computation that influenced decades of language design.
- **Alonzo Church** developed the lambda calculus, a formal system for expressing computation that became a theoretical foundation for functional programming languages.
- **Grace Hopper** championed the development of FLOW-MATIC in the 1950s, a business-oriented English-like language that directly influenced the design of COBOL. Her vision of human-readable programming was initially dismissed by contemporaries but ultimately transformed software development.

## The Readability–Efficiency Tension

Throughout the history of programming languages, a central tension has existed between human readability and machine efficiency. Early machine code and assembly languages prioritized direct hardware control but were difficult to write and maintain. High-level languages like FORTRAN, LISP, and COBOL introduced abstractions that made programming more accessible, but at the cost of less direct control over hardware. This trade-off continues to shape language design, with each generation of languages attempting to find new balances between expressiveness and performance. The work of figures like Backus, McCarthy, Church, and [[grace-hopper]] illustrates different points on this spectrum — from FORTRAN's focus on efficient numerical computation, to LISP's emphasis on symbolic expressiveness, to COBOL's readability for business applications.

## Web and Scripting Languages (1995–Present)

JavaScript, created by Brendan Eich at Netscape in 1995, became the dominant language for client-side web interactivity. It was standardized as ecmascript (ECMA-262), with Node.js extending its runtime to server-side development. Alongside html and css, JavaScript forms the core triad of front-end web development. Its event-driven, prototype-based design and ubiquity in browsers made it one of the most widely deployed programming languages in history.

## LISP and Symbolic Computation (1958)

John McCarthy at MIT designed LISP (List Processing) in 1958, influenced by [[alonzo-church]]'s lambda calculus. LISP was built around lists as the primary data structure and introduced recursive function definitions, automatic memory management through garbage collection, and the concept that code and data have the same representation — a list can be both a program and data that programs manipulate. ^[wexelblat-history-of-programming-languages-1981.txt:19-19]

LISP became the dominant language of [[artificial-intelligence-history|artificial intelligence]] research. Its flexibility and introspective capabilities made it well suited to symbolic AI tasks such as theorem proving, game playing, and natural language processing. McCarthy received the ACM Turing Award in 1971. ^[wexelblat-history-of-programming-languages-1981.txt:21-21]

## Structured Programming (1968–1970s)

In 1968, Edsger Dijkstra published a letter titled "Go To Statement Considered Harmful" in Communications of the ACM, arguing that unrestricted use of the goto instruction made programs difficult to understand and verify. The letter catalysed the structured programming movement, which advocated organising programs as compositions of three control structures: sequence, selection (if/else), and iteration (loops). ^[wexelblat-history-of-programming-languages-1981.txt:31-31]

Structured programming became the dominant pedagogical and practical approach through the 1970s. Languages like Pascal, designed by Niklaus Wirth in 1970, were explicitly designed to enforce structured programming discipline. C, developed at Bell Labs by Dennis Ritchie in 1972, provided structured programming constructs while retaining low-level access to hardware. ^[wexelblat-history-of-programming-languages-1981.txt:33-33]

## Object-Oriented Programming (1967–1995)

Simula 67, designed by Ole-Johan Dahl and Kristen Nygaard at the Norwegian Computing Centre, introduced the class and object concepts — grouping data and the operations on that data into a single unit. Smalltalk, developed at Xerox PARC through the 1970s by Alan Kay and others, radicalised this approach: in Smalltalk, everything is an object, and computation proceeds entirely through message passing between objects. ^[wexelblat-history-of-programming-languages-1981.txt:37-37]

C++, developed by Bjarne Stroustrup at Bell Labs in 1985, brought object-oriented programming to the C language and to systems programming. Java, released by Sun Microsystems in 1995, combined object orientation with a virtual machine that provided portability across hardware platforms — "write once, run anywhere." Python, designed by Guido van Rossum and first released in 1991, combined object orientation with dynamic typing and a focus on readability. ^[wexelblat-history-of-programming-languages-1981.txt:39-39]

## Type Systems and Language Theory

A type system assigns types to expressions in a program and uses them to detect errors before execution. Static type systems (C, Java, Haskell) check types at compile time; dynamic type systems (Python, JavaScript, LISP) check at runtime. Strong typing prevents operations that are undefined for a given type; weak typing allows implicit conversions between types. ^[wexelblat-history-of-programming-languages-1981.txt:43-43]

Formal language theory, developed by Noam Chomsky for linguistics and adapted for programming languages, provides a framework for describing syntax rigorously. Backus-Naur Form (BNF), introduced to describe ALGOL 60, became the standard notation for specifying programming language grammars. Type theory, developed in mathematics by Bertrand Russell and later refined by Per Martin-Löf, provides a foundation for reasoning about program correctness. ^[wexelblat-history-of-programming-languages-1981.txt:45-45]

## Modern Language Development

Functional programming languages such as Haskell (1990), derived from earlier work on ML and Miranda, formalised a style in which programs are composed of pure functions without side effects. Rust (2015), developed at Mozilla, introduced a type system that enforces memory safety at compile time without a garbage collector, enabling systems programming without the memory errors endemic to C. The diversity of contemporary languages reflects the persistence of the core tensions in language design: between safety and performance, between abstraction and control, between expressiveness and verifiability. ^[wexelblat-history-of-programming-languages-1981.txt:49-49]