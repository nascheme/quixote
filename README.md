# Quixote

![Don Quijote and Sancho Panza](https://raw.githubusercontent.com/nascheme/quixote/main/doc/images/Don_Quichotte_Honoré_Daumier.jpg)<br>
*Don Quijote and Sancho Panza, drawn by Honoré Daumier*

Quixote is a framework for developing Web applications in Python.
The target is web applications that are developed and maintained by
Python programmers.

The [release notes](doc/RELEASE_NOTES.md) contains important information about
changes in the most recent release.

See the [installation instructions](doc/INSTALL.txt). For
the impatient, use "uv" to install:

```
uv sync
```

Then you can run the mini demo:

```
uv run src/quixote/demo/mini_demo.py
```

Note that you can copy the `mini_demo.py` file somewhere and use it as a
starting point for your application if you like.

To run the full demo (server listens on http://localhost:8082/):

```
uv run python -m quixote run --port 8082
```

Documentation is available in the [doc/](doc/) directory.

Quixote includes PTL, the Python Template Language for producing
HTML with Python code. Note that the use of PTL is not required in
Quixote applications. Details about [PTL](doc/PTL.txt) are provided.


## Authors, copyright, and license

Quixote is copyrighted and made available under open source
licensing terms. See [LICENSE.txt](LICENSE.txt) for the details. The
[ACKS.txt](ACKS.txt) file lists people who have assisted in the development
of Quixote. [RELEASE_NOTES.md](RELEASE_NOTES.md) summarizes the changes in
the current release.

The painting by Honoré Daumier was photographed by Wikipedia user
[Yelkrokoyade](https://commons.wikimedia.org/wiki/File:Don_Quichotte_Honor%C3%A9_Daumier.jpg)
who has made it available under a Creative Commons license.


## Source code

The source code is managed using Git. You can check out a copy using the
command:

```
git clone https://github.com/nascheme/quixote.git
```
