## Description

This project is a simple command-line-based search engine that crawls the website [quotes.toscrape.com](https://quotes.toscrape.com/), builds an inverted index from the textual content of its pages, and allows users to search for keywords or phrases. The system ranks results based on keyword frequency and proximity, enabling basic relevance-based retrieval.

## Function Descriptions

### `word_tokenizer(text)`
Tokenizes the input text into lowercase alphabetic words, filters out stopwords and punctuation.

- **Parameters:** `text` (string) – the input text to tokenize
- **Returns:** List of cleaned word tokens

---

### `build_index()`
Crawls the [quotes.toscrape.com](https://quotes.toscrape.com/) website, extracts text content, tokenizes it, and builds an inverted index mapping each word to the pages and positions where it appears. The index is saved to a `JSON` file.

- **Side Effects:** Writes `inverted_index.json` file to disk
- **Wait Time:** Includes a 6-second politeness delay between requests

---

### `load_index()`
Loads the inverted index from a previously saved `inverted_index.json` file.

- **Returns:** Dictionary representing the inverted index

---

### `print_index(inverted_index, word)`
Prints the pages and positions of the specified word from the loaded inverted index.

- **Parameters:**
  - `inverted_index` (dict) – the loaded index
  - `word` (string) – the word to search for

---

### `power_set(lst)`
Generates all non-empty subsets of the input list, used to expand multi-word search queries.

- **Parameters:** `lst` (list) – a list of words
- **Returns:** List of all non-empty subsets of the input list, ordered from longest to shortest

---

### `find_query(inverted_index, words)`
Processes a search query by finding the intersection of pages containing all query tokens, ranking them based on frequency and positional distance.

- **Parameters:**
  - `inverted_index` (dict) – the loaded inverted index
  - `words` (list) – list of query terms
- **Output:** Prints top-ranked pages with frequency and distance scores

---

### `__main__` Interactive CLI
Provides an interactive command-line interface for the user to:

- `build` the index
- `load` a previously saved index
- `print` word-specific results from the index
- `find` relevant pages based on user queries
- `exit` the program

## Requirements

To run this project, you need the following:

### Python
- Python 3.6 or higher

### Python Packages
Install the required packages using pip:

```bash
pip install -r requirements.txt
```

To run the program:

```bash
python search.py
```
