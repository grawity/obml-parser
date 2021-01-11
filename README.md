Opera Mini OBML "Saved pages" converter
=======================================

This script will convert `.obml` and `.obml16` files that were saved using Opera Mini into HTML files which can be opened in any web browser.

Usage
-----

The program requires Python 3. There are no external dependencies besides that, so you can just run:

    ./obml-parser *.obml

Notes
-----

**Why is text misaligned?**

Note that because OBML files are the output of Opera's HTML rendering engine, many elements are pixel-positioned according to the *original device's* screen size and font metrics. Because many J2ME devices had custom fonts (optimized for low-res screens), it's possible that your computer will show the same text as too-tall or too-wide, and lines may overlap.

It may be possible to work around this by editing `font_sizes` and `line_height` at the top of the script.

This is nothing specific to the converter &ndash; your saved pages would look similarly misaligned if they were copied into a different J2ME device and opened with the real Opera Mini.

**What's up with hyperlinks?**

OBML does not have `<a href=...>`, i.e. you cannot actually have text that is also a link. Instead the engine outputs text and links as two separate layers &ndash; first it places the actual text at position `(X,Y)`, then overlays it with "link" rectangles at position `(X,Y,W,H)`.

So when you're viewing the page on a different device, links will appear to be misaligned &ndash; but it's actually the *text* which will shift around (due to different font metrics) while the links remain in their original position.

(The converter could do some guessing, but if you have a chunk of text in which only some words are linked, then it is very difficult to programmatically determine which specific words were originally covered by the link rectangles.)

**Other interesting things**

OBML does not have styled widgets the way HTML would. The style is actually pre-rendered, and those pretty 3D effects are made out of pixel-positioned lines and rectangles. Even button gradients are pre-rendered and drawn as a series of 1-pixel thin lines.
