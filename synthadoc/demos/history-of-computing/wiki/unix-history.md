---
aliases: []
confidence: high
created: 2026-04-08
orphan: false
sources:
- file: public-domain/ritchie-unix-history-1979.txt
  hash: placeholder
  ingested: 2026-04-08
  size: 0
status: active
tags:
- unix
- operating-system
- bell-labs
- c-language
title: Unix History
type: technology
updated: '2026-07-12'
---
# Unix History

Unix is a family of multitasking, multiuser operating systems that descend from the original AT&T Unix, developed at Bell Labs by Ken Thompson, Dennis Ritchie, and others starting in 1969.

## Origins

After the Multics project (a collaboration between Bell Labs, MIT, and GE) was cancelled for Bell, Ken Thompson began writing a smaller operating system on a discarded PDP-7. The name "Unix" was a pun on Multics. Dennis Ritchie later joined and the system was ported to the PDP-11.

## The C Language

To make Unix portable across hardware, Dennis Ritchie developed the C programming language (1972). C allowed Unix to be rewritten in a high-level language, making it the first widely portable OS. This was a watershed moment in [[programming-languages-overview]]: a systems language that was both expressive and close to the [[von-neumann-architecture]] hardware.

## BSD and the Open Source Lineage

The University of California, Berkeley produced the Berkeley Software Distribution (BSD) starting in 1977. BSD added virtual memory, TCP/IP (critical to [[internet-origins]]), and the fast file system. From BSD descended FreeBSD, OpenBSD, NetBSD, and macOS.

## Linux

In 1991, Linus Torvalds released Linux, a Unix-like kernel written from scratch. Combined with GNU tools, Linux became the dominant server and cloud operating system. The GNU/Linux ecosystem became the foundation of the [[open-source-movement]].

## Legacy

The design philosophy of Unix — small, composable tools that do one thing well — influenced everything from shell scripting to modern microservice architecture. The [[alan-turing]] Award was given to Thompson and Ritchie in 1983 for developing Unix.

## Pipes, Filters, and the Unix Philosophy

Unix established a design philosophy — articulated most clearly by Douglas McIlroy — centred on composability. The principle is that each program should do one thing well, accept text input, and produce text output. Programs are composed by connecting them with pipes, a mechanism that routes the output of one process directly to the input of another without writing an intermediate file. ^[ritchie-unix-history-1979.txt:27-27]

This design emerged from practical experience: programs written as filters could be combined in novel ways their authors had not anticipated. A user wanting to count the unique words in a file could compose the sort, uniq, and wc commands without writing any new code. The pipe and filter model influenced the design of later languages, shells, and distributed systems. ^[ritchie-unix-history-1979.txt:29-29]

## Licensing and the Berkeley Fork

AT&T licensed Unix to universities at low cost, making it widely available for academic use. The University of California, Berkeley became a major centre of Unix development. Starting in 1977, Berkeley's Computer Systems Research Group (CSRG) produced the Berkeley Software Distribution ([[bsd]]), which added significant new features: a virtual memory system, a faster file system, and — critically for the growth of the internet — a complete implementation of the TCP/IP networking protocols in 1983. ^[ritchie-unix-history-1979.txt:33-33]

BSD's networking code was picked up by many commercial Unix vendors and became the foundation on which the internet ran. BSD also generated several long-lived descendants: FreeBSD, OpenBSD, and NetBSD continue in active development, and Apple's macOS and iOS are derived from BSD through the NeXTSTEP operating system. ^[ritchie-unix-history-1979.txt:35-35]

## C Language Lineage

Dennis Ritchie developed C by building on prior language work: BCPL, developed by Martin Richards, and its derivative B, created by [[ken-thompson]]. Ritchie redesigned the type system and language structure to suit the PDP-11's architecture, producing C in its first published form by 1972. Ritchie and Brian Kernighan documented the language in "The C Programming Language" (1978), one of the best-selling technical books in computing history. ^[ritchie-unix-history-1979.txt:19-23]

## The Turing Award

Ken Thompson and Dennis Ritchie received the ACM Turing Award in 1983 for their development of Unix, recognising the system's enormous influence on subsequent operating systems, programming languages, and software culture. ^[ritchie-unix-history-1979.txt:39-39]