---
aliases: []
categories:
- Early Computing & Pioneers
confidence: high
contradiction_note: 'Flagged while ingesting ''first-compiler-controversy.pdf'': The
 source directly disputes claims in two existing wiki pages. It argues that Grace
 Hopper''s A-0 system was NOT a compiler but a linker/loader, and that the IBM FORTRAN
 compiler (1957, John Backus) deserves priority as the first true compiler. The ''grace-hopper''
 page has status=''contradicted'' which aligns with this dispute. The source explicitly
 says the A-0-as-first-compiler claim is a ''persistent myth'' and cites IEEE Annals
 of the History of Computing to support the correction. This is a clear factual dispute
 about claims made in the grace-hopper page. Per RULE 1, this should be flagged.
 The target is ''grace-hopper'' since that page contains the disputed claims about
 A-0.'
created: 2026-04-09
lint_warnings:
- claim: Hopper earned her bachelor's degree in mathematics and physics from Vassar
 College in 1928, then completed her master's and doctoral degrees in mathematics
 at Yale University.
 concern: Hopper earned her bachelor's degree in mathematics and physics, but this
 is slightly misleading—she received a bachelor's in mathematics only; physics
 was part of her combined program. More importantly, her PhD from Yale was in mathematics
 (1934), which is correct, but the phrasing 'master's and doctoral degrees' is
 fine. Actually, this claim is largely defensible. However, the bachelor's was
 in mathematics, not 'mathematics and physics' as a dual degree. Vassar awarded
 her a BA in mathematics.
- claim: A-0 allowed a programmer to write mathematical expressions using symbolic
 notation that the system would then translate into machine code.
 concern: This is contradicted by the page's own discussion, which acknowledges that
 A-0 was more accurately a linker/loader that combined pre-written subroutines
 rather than translating symbolic expressions into machine code. The claim that
 A-0 'translate[d]' symbolic notation into machine code overstates what the system
 actually did.
orphan: false
sources:
- file: public-domain/hopper-biography-usn.txt
 hash: placeholder
 ingested: 2026-04-09
 size: 0
- file: C:\Users\ladmin\wikis\history-of-computing\raw_sources\public-domain\hopper-biography-usn.txt
 hash: d1d5876c8832651fbfd126491f3af3398ce127ad5835bcf733e023a20b307733
 ingested: '2026-07-12'
 size: 5112
status: contradicted
tags:
- biography
- compilers
- cobol
- navy
title: Grace Hopper
type: person
updated: '2026-07-12'
---

# Grace Hopper

Grace Brewster Murray Hopper (1906–1992) was an American computer scientist and United States Navy rear admiral. She pioneered the idea that programs could be written in human-readable language and automatically translated to machine instructions — an idea her contemporaries dismissed as impossible.

## Education and Early Career

Hopper earned her bachelor's degree in mathematics and physics from Vassar College in 1928, then completed her master's and doctoral degrees in mathematics at Yale University. She joined the Vassar faculty and taught mathematics until World War II drew her into military service.

## Naval Service and the Harvard Mark I

In 1944, Hopper was assigned to the Bureau of Ships Computation Project at Harvard University, where she worked under Howard Aiken on the Harvard Mark I, a large-scale electromechanical computer. She was one of the first programmers ever assigned to such a machine, writing operational manuals and developing the conceptual framework for treating sequences of machine instructions as reusable procedures — a precursor to the subroutine concept.

## The Origin of "Debugging"

On 9 September 1947, operators of the Harvard Mark II traced a malfunction to a moth trapped in a relay. The insect was taped into the logbook with the note "First actual case of bug being found." Although the term "bug" for engineering defects predates this incident, the Mark II logbook entry is the event most directly associated with the popularization of "debugging" in computing. Hopper's contribution was spreading the term within the programming community, not coining it from scratch.

## UNIVAC I and the Eckert-Mauchly Years

After the war, Hopper joined the Eckert-Mauchly Computer Corporation (later absorbed into Remington Rand), where she worked on the UNIVAC I, one of the first commercially produced electronic computers. Her collaboration with J. Presper Eckert and John Mauchly placed her at the center of early commercial computing in the United States.

## The A-0 System and the Question of the "First Compiler"

In 1952, Hopper developed the A-0 system for the UNIVAC I. A-0 allowed a programmer to write mathematical expressions using symbolic notation that the system would then translate into machine code. For many years, A-0 was widely credited in popular accounts and biographical summaries as the first compiler — a program that translates human-readable source code into machine-executable instructions.

However, this attribution has been challenged by some historians of computing. Critics, including authors cited in recent scholarship such as the "first-compiler-controversy" source, argue that A-0 was more accurately a linker or loader rather than a true compiler in the modern sense, since it primarily combined pre-written subroutines into executable programs rather than translating higher-level source code. From this perspective, the IBM FORTRAN compiler released in 1957 is often identified as the first genuine compiler, because it performed full source-to-machine-code translation with significant optimization.

The distinction hinges on how one defines a "compiler": under a broad definition that includes any system automating the production of machine code from symbolic input, A-0's claim is defensible; under a stricter definition requiring translation of source language into equivalent machine code, the title tends to be assigned to FORTRAN. Both views remain present in the historical literature.

## COBOL and Later Contributions

Hopper's work on A-0 led to subsequent systems including A-1, A-2, and FLOW-MATIC, the latter of which directly influenced the development of COBOL (Common Business-Oriented Language) in 1959. COBOL was one of the first high-level programming languages designed to be readable by non-specialists, and its creation reflected Hopper's persistent advocacy for programming languages that resembled natural English.

## Legacy

Hopper retired from the Navy in 1986 with the rank of rear admiral, one of the few women to hold that rank at the time. She was recalled to active duty and continued working until shortly before her death in 1992. The annual Grace Hopper Celebration, named in her honor, is one of the largest gatherings of women in computing. Whether or not A-0 qualifies as the first compiler, Hopper is broadly recognized for advancing the idea that computers could be programmed in terms closer to human language — a conceptual contribution that shaped the trajectory of software development.

## Sources

- hopper-biography-usn: U.S. Navy biographical entry on Grace Hopper.
- first-compiler-controversy: Independent source challenging the A-0 "first compiler" attribution.

## The "First Bug" and the Origin of Debugging

Hopper's work on the Harvard Mark I and its successors — the Mark II and Mark III — gave her deep familiarity with how computers executed instructions and where they failed. It was during work on the Mark II in 1947 that her team discovered a moth lodged in a relay, causing a malfunction. They taped the moth into the logbook with the annotation "first actual case of bug being found," providing the literal origin of the now-universal term debugging. ^[hopper-biography-usn.txt:13-13]

## The UNIVAC I and the 1952 Election

After the war, Hopper joined the Eckert-Mauchly Computer Corporation, where she worked on the UNIVAC I, one of the first commercial computers sold in the United States. The UNIVAC I became famous in 1952 when CBS used it to predict the outcome of the U.S. presidential election on live television. ^[hopper-biography-usn.txt:17-17]

## Naval Career Milestones

Hopper's naval career extended far beyond her wartime assignment. She was recalled to active duty multiple times and eventually achieved the rank of rear admiral in 1985, the highest rank achieved by a woman in the United States Navy to that point. She retired from active duty in 1986 at the age of 79, making her the oldest serving officer on active duty in the Navy.

She was awarded the National Medal of Technology in 1991 and the Presidential Medal of Freedom posthumously in 2016. ^[hopper-biography-usn.txt:31-33]

## Honors and Legacy

- The Grace Hopper Celebration of Women in Computing, first held in 1994, is the world's largest gathering of women technologists and bears her name.
- The USS Hopper, a guided-missile destroyer commissioned in 1997, was named in her honour.
- Hopper's enduring contribution was insisting that computers should serve human language, not the reverse — a principle that underlies every high-level language developed since the 1950s. ^[hopper-biography-usn.txt:37-39]

## From hopper-biography-usn.txt

# Synthadoc demo content — released to the public domain (CC0). Factual summary for demonstration purposes.

Grace Brewster Murray Hopper (1906–1992) was an American computer scientist, mathematician, and United States Navy rear admiral. Her career spanned more than four decades of active service and pioneering software development, during which she fundamentally changed how programmers interact with computers. ^[hopper-biography-usn.txt:3-3]

## Early Life and Education

Hopper was born in New York City on 9 December 1906. She earned a bachelor's degree in mathematics and physics from Vassar College in 1928, followed by a master's degree and a doctorate in mathematics from Yale University in 1934. She was among the few women in the United States to hold a doctorate in mathematics at the time. She taught mathematics at Vassar from 1931 until she joined the Navy during the Second World War. ^[hopper-biography-usn.txt:7-7]

## Naval Service

Hopper enlisted in the United States Navy Reserve in 1943, receiving a commission as a lieutenant junior grade. She was assigned to the Bureau of Ships Computation Project at Harvard University, where she worked with Commander Howard Aiken on the Harvard Mark I, one of the earliest large-scale electromechanical computers. The Mark I was 51 feet long and performed arithmetic by reading instructions punched on paper tape. ^[hopper-biography-usn.txt:11-11]

Hopper's work on the Mark I and its successors — the Mark II and Mark III — gave her deep familiarity with how computers executed instructions and where they failed. It was during work