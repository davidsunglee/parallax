# Wire Values have one canonical storage and transport encoding

`m-wire` owns one canonical output spelling for every Neutral Type wherever a
Wire Value crosses a storage or transport serde seam. UTC timestamps use `Z`,
decimals retain their declared scale, and bytes use lowercase hexadecimal;
individual document codecs, language renderers, conformance adapters, and
fixtures do not choose equivalent alternate spellings. Structured Columns
persist these same values, so changing a canonical Wire spelling is a
storage-format migration rather than a presentation change. Centralizing the
encoding prevents semantically equal values from drifting across storage,
runtime, and conformance while leaving each consuming module responsible for
where and how the encoded value participates in its own behavior.
