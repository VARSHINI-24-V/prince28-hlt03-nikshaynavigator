# Capacity plan: NikshayNavigator

Full corpus target: All applicable guidelines, modules and circulars (5,000+ pages).

<!-- generated:start -->

## Generated capacity measurements

- **Full corpus target:** 5,000 pages
- **Measured files:** 15
- **Measured PDF pages:** 1,382
- **Measured extractable text:** 2,442,734 characters
- **Measured token estimate:** ~610,684 tokens
- **Measured tokens per PDF page:** ~441.9
- **Chunk size assumption:** 500 tokens
- **Embedding dimensions:** 1,024
- **Projected full-corpus tokens:** ~2,209,422
- **Projected chunks:** ~4,419
- **Estimated embedding cost:** USD $0.4419
- **Estimated embedding cost in INR:** Rs 41.98
- **Projected float32 vector storage:** ~17.26 MB
- **Approximate extracted-text storage:** ~8.43 MB
- **Measured raw-file storage today:** 177.82 MB

### Assumptions and limitations

- Token estimates use extracted characters divided by four; no model tokenizer was run.
- Embedding cost assumes the supplied price per million tokens and excludes retries, storage, indexing and application costs.
- Vector storage assumes four bytes per dimension and excludes PostgreSQL indexes and row overhead.
- Extracted-text storage is approximate and excludes metadata and database overhead.
- Scanned PDFs may need OCR; their extracted-text and token estimates may be too low.
- Compare the projected text and vector storage with the actual free-space limit shown in your PostgreSQL provider dashboard.

<!-- generated:end -->

## What I conclude


## What I conclude

1. **Is embedding cost a problem?**

   The projected one-time embedding cost for 5,000 pages is approximately Rs 41.98, using the assumed USD 0.20 per million tokens and USD-INR rate of 95. This is an estimate, not a live API quotation.

2. **Do vectors and extracted text fit in my free PostgreSQL?**

   Projected float32 vector storage is approximately 17.26 MB. Extracted text is approximately 8.42 MB. Database indexes, metadata and row overhead require additional storage. I will compare these estimates against my actual Neon database storage limit before concluding.

3. **Which estimate am I least sure about?**

   The token estimate is least certain because it uses extracted characters divided by four. I will use the actual embedding model's tokenizer and review PDFs with poor text extraction.

4. **What changes if the corpus grows 10 times?**

   At approximately 50,000 pages, the projected corpus would contain 22.09 million tokens and 44,189 chunks. Estimated embedding cost becomes Rs 419.80 and vector storage approximately 172.6 MB, assuming the same embedding dimensions and chunk size. Database storage and processing requirements also increase.
