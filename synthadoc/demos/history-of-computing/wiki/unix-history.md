---
title: Unix History
tags: [unix, operating-system, bell-labs, c-language]
status: active
confidence: high
created: 2026-04-08
sources:
  - file: public-domain/ritchie-unix-history-1979.txt
    hash: placeholder
    size: 0
    ingested: 2026-04-08
aliases: []
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
