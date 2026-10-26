# Property Testing

Every project in the series is checked with **property-based tests**. Here's
the idea, once, and then a list of where to see it in action.

## The idea

Imagine you've built a vending machine. The usual way to check it: put in
a pound, press B4, and see a packet of crisps drop out. That's an **example
test**. It's useful, but it only tells you about the one snack you thought
of.

Now imagine a mischievous tester. All night they press every button there is:
coins and no coins, two buttons at once, a snack that's sold out, the same
button forty times. For each go they check a single rule, such as:

> Whatever you press, the money you put in always equals the price of what
> came out plus the change you got back.

That rule is a **property**. It doesn't say which snack comes out. It says
something that must be true *every* time, whatever happens.

When the tester finds something that breaks the rule, they don't just write
"it went wrong after about a hundred presses". They play it again with less
and less -- fewer coins, fewer buttons, smaller numbers -- checking it still
goes wrong each time, until it's as simple as it can be. That boiling-down is
called **shrinking**, and it's the best part: the smallest failing input
usually points straight at the bug.

In Python, the tester is a library called
[Hypothesis](https://hypothesis.readthedocs.io/). Each project has a page
that walks through one of its properties, line by line.

## A property from every project

In learning order, each with the rule its page walks through:

- **[PyOS](https://robcox2910.github.io/py-os/property-testing/)**: Every disk-arm policy visits each cylinder it was asked for exactly once: nothing lost, nothing made up.
- **[Pebble](https://robcox2910.github.io/pebble-lang/property-testing/)**: Whatever text you give `check`, it either says yes or raises a `PebbleError`, and never crashes.
- **[PyDB](https://robcox2910.github.io/pydb/property-testing/)**: A table saved to its file comes back exactly as it went in: schema, rows, next ID and indexes.
- **[PyKV](https://robcox2910.github.io/pykv/property-testing/)**: Whatever you save, loading gives back: the same keys, the same values, the same types.
- **[PyDocDB](https://robcox2910.github.io/pydoc-db/property-testing/)**: `find` gives exactly the documents a plain Python filter over the list would give.
- **[PyGraphDB](https://robcox2910.github.io/pygraphdb/property-testing/)**: Breadth-first search visits every place you can reach, each once, and nowhere else.
- **[PyTSDB](https://robcox2910.github.io/pytsdb/property-testing/)**: However you downsample, the buckets' counts and sums add up to the whole logbook's.
- **[PyVecDB](https://robcox2910.github.io/pyvecdb/property-testing/)**: Top-k search finds the same nearest vectors as measuring every one and sorting them.
- **[PyColDB](https://robcox2910.github.io/pycoldb/property-testing/)**: Compaction tidies up the files but never changes what a read returns.
- **[PyCrypt](https://robcox2910.github.io/pycrypt/property-testing/)**: Decrypting with the same shift gives back exactly the text you encrypted.
- **[PyNet](https://robcox2910.github.io/pynet/property-testing/)**: However the bytes are cut up on the way, the receiver gets exactly the frames that were sent.
- **[PyWeb](https://robcox2910.github.io/pyweb/property-testing/)**: Whatever request head you write out, reading it back gives the very same head.
- **[PyGit](https://robcox2910.github.io/pygit/property-testing/)**: A file's fingerprint always matches Git's own rule: SHA-1 of `blob <size>`, a zero byte, then the file.
- **[PySearch](https://robcox2910.github.io/pysearch/property-testing/)**: A search finds exactly what reading every book by hand would find, with the same scores, in the same order.
- **[PyMQ](https://robcox2910.github.io/pymq/property-testing/)**: A saved queue loads back with every message, in the same delivery order.
- **[PyLLM](https://robcox2910.github.io/pyllm/property-testing/)**: `backward()` gets the same slopes as nudging each number a little and measuring.
- **[PyScheduler](https://robcox2910.github.io/pyscheduler/property-testing/)**: Whatever values you list on a cron dial, parsing gives back exactly those values, and the fire times come out once each, in order.
- **[PyStack](https://robcox2910.github.io/pystack/property-testing/)**: Whatever a Pebble program stores with `kv_set`, the next run reads back exactly.
