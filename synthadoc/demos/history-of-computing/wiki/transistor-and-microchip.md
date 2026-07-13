---
aliases: []
confidence: high
created: 2026-04-09
orphan: false
sources:
- file: public-domain/riordan-hoddeson-crystal-fire.txt
  hash: placeholder
  ingested: 2026-04-09
  size: 0
status: active
tags:
- hardware
- transistor
- integrated-circuit
- moores-law
title: Transistor and Microchip
type: technology
updated: '2026-07-12'
---
# Transistor and Microchip

The transistor and the integrated circuit are the twin inventions that made modern computing physically possible. Without them, [[von-neumann-architecture]] computers would remain room-sized vacuum-tube machines consuming megawatts of power.

## The Transistor (1947)

John Bardeen, Walter Brattain, and William Shockley at Bell Labs demonstrated the first point-contact transistor on 16 December 1947. The transistor is a semiconductor device that amplifies or switches electrical signals. Unlike vacuum tubes, transistors are small, reliable, consume little power, and generate minimal heat. Bardeen, Brattain, and Shockley shared the 1956 Nobel Prize in Physics for the discovery.

## The Integrated Circuit (1958–1959)

Jack Kilby at Texas Instruments (1958) and Robert Noyce at Fairchild Semiconductor (1959) independently invented the integrated circuit — multiple transistors and their connections fabricated on a single piece of semiconductor. Kilby won the Nobel Prize in Physics in 2000; Noyce had died in 1990. The IC eliminated the "tyranny of numbers": hand-soldering thousands of discrete transistors was slow, expensive, and unreliable.

## Intel 4004 and the Microprocessor (1971)

Intel's 4004, designed by Federico Faggin, Ted Hoff, and Stanley Mazor, placed a complete CPU on a single chip for the first time. The 4004 contained 2,300 transistors and ran at 740 kHz. It was designed for a Japanese calculator company, but Intel recognised it as a general-purpose computing engine. The microprocessor made the [[personal-computer-revolution]] economically viable.

## Moore's Law

Gordon Moore, Intel co-founder, observed in 1965 that the number of transistors on a chip doubled roughly every two years at constant cost. This empirical trend held for over 50 years, driving exponential improvements in computing power and reductions in cost. Modern chips contain tens of billions of transistors at nanometre scales.

## Physical Limits

By the 2010s, transistors approached atomic dimensions. Classical scaling slowed, prompting the industry to pursue 3D chip stacking, chiplets, and specialised processors (GPUs, TPUs, NPUs) to continue performance improvements. The end of Moore's Law has accelerated interest in quantum computing and neuromorphic architectures.

See also: [[von-neumann-architecture]] for the logical design these chips implement; [[programming-languages-overview]] for the software abstraction layers above the hardware.

## Moore's Law

In 1965, [[gordon-moore]], then research director at Fairchild Semiconductor, published an observation in *Electronics* magazine: the number of components per integrated circuit had roughly doubled every year since the first ICs were manufactured. He projected the trend would continue for at least a decade and predicted that by 1975 it would be feasible to put 65,000 components on a single chip. ^[riordan-hoddeson-crystal-fire.txt:39-39] Moore revised his estimate to a doubling approximately every two years in 1975. ^[riordan-hoddeson-crystal-fire.txt:41-41] The empirical trend — known as Moore's Law — held for over fifty years, enabling chips to progress from hundreds of transistors in early ICs to tens of billions in modern processors. ^[riordan-hoddeson-crystal-fire.txt:41-41] The economic consequence, roughly constant cost per transistor as density increased, drove down the price of [[personal-computer-revolution|computing hardware]] continuously. ^[riordan-hoddeson-crystal-fire.txt:41-41]

## Intel 4004 and the Microprocessor (1971)

The microprocessor brought the entire [[von-neumann-architecture|central processing unit]] of a computer onto a single chip. Intel's 4004, designed by Federico Faggin, Ted Hoff, and Stanley Mazor, was fabricated using Intel's silicon-gate MOS process and contained 2,300 transistors on a chip roughly 3 mm by 4 mm. It operated at 740 kHz, processed 4 bits at a time, and could address 640 bytes of program memory. ^[riordan-hoddeson-crystal-fire.txt:45-45] The 4004's existence as a general-purpose CPU on a chip made the [[personal-computer-revolution|personal computer]] economically feasible. Subsequent Intel processors — the 8080 (1974), the 8086 (1978), and their descendants — powered the Altair, the IBM PC, and the industry of compatible machines that followed. ^[riordan-hoddeson-crystal-fire.txt:47-47]

## Physical Limits and the End of Classical Scaling

By the 2010s, transistors in leading-edge processors had gate lengths of a few nanometres, approaching atomic dimensions. Fundamental physical limits began to constrain continued scaling: quantum tunnelling caused leakage current at extremely small dimensions, and heat dissipation became a critical constraint. The simple scaling that had characterised Moore's Law began to slow. ^[riordan-hoddeson-crystal-fire.txt:51-51] The industry responded by moving from two-dimensional planar transistors to three-dimensional FinFET structures, and by stacking multiple chips vertically in packages. Specialised processors — GPUs for parallel computation, TPUs for machine learning inference, NPUs for neural network acceleration — complemented general-purpose CPUs, continuing the practical trajectory of Moore's Law even as classical transistor scaling reached its limits. ^[riordan-hoddeson-crystal-fire.txt:53-53]