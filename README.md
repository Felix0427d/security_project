# Security project

## Project's objectives
The goal of this project is to find a secret and password, both hashed, contained in an Arduino firmware. 

As materials, we got :
- Arduino UNO board
- ChipWhisper card (used to perform side channel attacks and fault injections during the labs)
- A .elf file we had to flash into the arduino
- Our good old computer
  
Options are quiet wide, but taking into account that we mostly worked on hardware attacks during the labs, we can therefore deduce that this way of proceeding should be prefered.

## Before it gets serious
First thingh I've done while going through this project, was the easy way. Trying to find the source code with the .elf file that was given as starting point. First I tried via a website, which gave me the strings but couldn't find the entire code. But our good old mister Claude foun'd a way to traduce the .elf into the source code (.cpp) super fastly. 

Fore sure this wasn't a good idea in terms of surprise when cracking this case, but as I couldn't resist, let's not be blind, this may (for sure) had inroduce in my way to see the project, a certain bias. That's why, a small mention of this is important.

-> Let's pretend this didn't happend

## First steps into the project
