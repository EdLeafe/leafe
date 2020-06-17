from __future__ import absolute_import, print_function, unicode_literals

import os
import re
import sys



MAX_LENGTH = 280
BREAK_ON_SENTENCE = True
END_TXT = " /end"
CONTINUATION = "..."
TEST_FILE = "towel.txt"
SENTENCE_END = r"[\.\?!]"
SENTENCE_END_PAT = re.compile(SENTENCE_END)
BREAK_CHARS = r"[:;,]"
BREAK_CHARS_PAT = re.compile(BREAK_CHARS)
NOT_PUNC = r"[^\.\?!;:,]+"
SEP = "^@^"
TOTAL_HOLDER = "@"
URL_PAT = re.compile(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+")
# All URLs count as 23 characters in tweets
URL_PLACEHOLDER = "@" * 23


tag_position = None
holder = None


def make_thread(txt, num_style, break_style, end_text):
    txt = remove_newlines(txt)
    pg_pat = _get_page_pattern(num_style, len(txt))
    tokens = tokenize(txt, break_style)
    chunks = chunker(tokens, num_style, pg_pat, end_text)
    if holder:
        chunks = [chunk.replace(holder, str(len(chunks))) for chunk in chunks]
    return chunks


def _get_page_pattern(num_style, txtlen):
    global tag_position, holder
    tag_position = num_style[-1]
    if num_style.startswith("nsn"):
        # Need to get a rough idea of the maximum number of chunks, so that we know how many spaces
        # to reserve for the total in 1/N style numbering. For this, take the total length divided
        # by the max per tweet, and double it.
        maxnum = int(txtlen / MAX_LENGTH) * 2
        holder = (TOTAL_HOLDER * len(str(maxnum)))
        pg_pat = "{}/" + holder
        if tag_position == "b":
            pg_pat = pg_pat + " "
        else:
            pg_pat = " " + pg_pat
    else:
        pg_pat = "{}/ " if tag_position == "b" else " /{}"
    return pg_pat


def remove_newlines(txt):
    t1 = re.sub(r"[\n\r]+", r"\n", txt)
    return re.sub(r"\n", " ", t1)


def rejoin(fragments, separators, num):
    frags = fragments[:num]
    seps = separators[: num - 1]
    frag_join = "{}".join(frags)
    return frag_join.format(*seps)


def reduce_urls(txt):
    """Twitter counts all URLs as only 23 characters, so this replaces all URLs
    in the text with a 23-character placeholder.
    """
    return URL_PAT.sub(URL_PLACEHOLDER, txt)


def split_sentence(sentence, pg_txt):
    # see if there is any punctuation in the second half of the sentence that
    # would be a natural break point
    senlen = len(sentence)
    len_pg_txt = len(pg_txt)
    midpoint = senlen / 2
    fragments = BREAK_CHARS_PAT.split(sentence)
    separators = BREAK_CHARS_PAT.findall(sentence)
    pos = 0
    if separators:
        shorter = sentence
        pos = num_frags = len(fragments)
        while len(shorter) + len_pg_txt > MAX_LENGTH and pos > 0:
            shorter = shorter.rstrip(fragments[pos - 1])
            pos -= 1
    if pos:
        extra = sentence.lstrip(shorter)
        if tag_position == "e":
            extra = extra.rstrip(pg_txt).strip(" ")
            shorter = shorter.rstrip() + pg_txt
        else:
            extra = extra.lstrip(pg_txt).strip(" ")
            shorter = pg_txt + shorter.rstrip()
        return shorter, extra
    else:
        # Cannot split into smaller parts based on break characters. Just find the word break that
        # maximizes the chunk.
        max_sentence_length = MAX_LENGTH - len_pg_txt
        max_short = sentence[:max_sentence_length]
        try:
            last_space = max_short.rindex(" ")
        except ValueError:
            # No way to separate; just return the longest substring
            max_sentence_length = MAX_LENGTH - len_pg_txt - len(CONTINUATION)
            if tag_position == "e":
                shorter = sentence[:max_sentence_length] + CONTINUATION + pg_txt
            else:
                shorter = pg_txt + sentence[:max_sentence_length] + CONTINUATION
            extra = sentence[max_sentence_length + 1 :]
            return shorter, extra
        if tag_position == "e":
            shorter = sentence[:last_space] + pg_txt
        else:
            shorter = pg_txt + sentence[:last_space]
        extra = sentence[last_space + 1 :]
        return shorter, extra


def chunker(tokens, num_style, pg_pat, end_text):
    pos = 0
    sentences = []
    sentence_end = 0
    from utils import logit
    logit("TOKENS AT START", tokens)
    while True:
        try:
            sentence_end = tokens.index(SEP)
        except ValueError:
            # Add the last bit
            sentences.append(" ".join(tokens[-1:]))
            logit("LAST", sentence_end, tokens[-1:])
            break
        sentences.append(" ".join(tokens[:sentence_end]))
        tokens = tokens[sentence_end + 1 :]
    chunks = []
    to_skip = 0
    for pos, sentence in enumerate(sentences):
        if to_skip:
            to_skip -= 1
            continue
        sentence = sentence.strip()
        chunk_num = len(chunks) + 1
        pg_txt = pg_pat.format(chunk_num)
        args = (sentence, pg_txt) if tag_position == "e" else (pg_txt, sentence)
        proposed_with_pg_txt = "{}{}".format(*args)
        len_proposed_with_pg_txt = len(reduce_urls(proposed_with_pg_txt))

        # Need to iterate through long sentences until done.
        while len_proposed_with_pg_txt > MAX_LENGTH:
            proposed_with_pg_txt, extra = split_sentence(sentence, pg_txt)
            chunks.append(proposed_with_pg_txt)
            sentence = extra.strip()
            chunk_num = len(chunks) + 1
            pg_txt = pg_pat.format(chunk_num)
            args = (sentence, pg_txt) if tag_position == "e" else (pg_txt, sentence)
            proposed_with_pg_txt = "{}{}".format(*args)
            len_proposed_with_pg_txt = len(reduce_urls(proposed_with_pg_txt))
        proposed = proposed_with_pg_txt
        len_proposed = len(reduce_urls(proposed))

        ahead = 1
        # See if we can add more sentences.
        while True:
            extra_room = MAX_LENGTH - len_proposed
            try:
                next_sentence = sentences[pos + ahead]
            except IndexError:
                # At the end of the text; need to change the pg_txt for the last chunk
                if len(chunks):
                    # If no end_text, leave the tag as is
                    if end_text:
                        end_pat = "{}/ " if tag_position == "b" else " /{}"
                        proposed = proposed.replace(pg_txt, end_pat.format(end_text))
                else:
                    # Just a single chunk, so remove the pg_txt.
                    proposed = proposed.replace(pg_txt, "")
                break
            if len(reduce_urls(next_sentence)) < extra_room:
                # Add that to the current chunk
                if tag_position == "e":
                    proposed = "{} {}{}".format(proposed.rstrip(pg_txt), next_sentence, pg_txt)
                else:
                    proposed = "{}{} {}".format(pg_txt, proposed.lstrip(pg_txt), next_sentence)
                to_skip += 1
                ahead += 1
                len_proposed = len(reduce_urls(proposed))
            else:
                break
        # We've reached the maximum size.
        chunks.append(proposed)
    return chunks


def tokenize(txt, break_style):
    tokens = []

    def spc(scn, txt):
        pass

    def snt(scn, txt):
        brk(scn, txt)
        tokens.append(SEP)

    def brk(scn, txt):
        if tokens:
            tokens[-1] += txt
        else:
            tokens.append(txt)

    def char(scn, txt):
        tokens.append(txt)

    # The text may contain URLs that have punctuation that we don't want to
    # break on, so reduce them with the placeholders, and then restore the URLs
    # afterwards.
    urls = URL_PAT.findall(txt)
    reduced_text = reduce_urls(txt)
    if break_style == "sentence":
        scanner = re.Scanner(
            [(r" ", spc), (SENTENCE_END, snt), (BREAK_CHARS, brk), (NOT_PUNC, char),]
        )
    else:
        scanner = re.Scanner(
            [(r" ", spc), (SENTENCE_END, snt), (BREAK_CHARS, snt), (NOT_PUNC, char),]
        )
    scanner.scan(reduce_urls(txt))
    # Now replace the URLs where their placeholders were
    for pos, token in enumerate(tokens):
        while urls and URL_PLACEHOLDER in token:
            tokens[pos] = token = token.replace(URL_PLACEHOLDER, urls[0], 1)
            urls.pop(0)
    return tokens


def main():
    if len(sys.argv) < 2:
        fname = TEST_FILE
        number_style = "sne"
        break_at =  "sentence"
        end_text = "/end"
    else:
        fname = sys.argv[1]
        if not os.path.exists(fname):
            raise IOError("The file '{}' does not exist".format(name))
        number_style = sys.argv[2] if len(sys.argv) > 2 else "sne"
        break_at = sys.argv[3] if len(sys.argv) > 3 else "sentence"
        end_text = sys.argv[4] if len(sys.argv) > 4 else "/end"
    with open(fname) as ff:
        txt = ff.read()
    txt = remove_newlines(txt)
    chunks = make_thread(txt, number_style, break_at, end_text)
    for chunk in chunks:
        print(chunk)


if __name__ == "__main__":
    main()
