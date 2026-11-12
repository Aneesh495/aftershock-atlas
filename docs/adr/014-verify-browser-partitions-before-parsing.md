# 014: Verify browser partitions before parsing

Static publication can mix a cached data partition with a newer deployment index. Historical selectors make this failure consequential: a plausible JSON file can still belong to the wrong source revision.

Declare every public data file's SHA256 in the snapshot index. Add the expected hash to request identity, stream at most 32 MB, verify WebCrypto SHA256 and only then parse or cache JSON. Clear prepared exports when a view changes or fails, and disable export until its asynchronous setup completes. A repaired source can be retried; a full reload fetches the current index.

This checks consistency with the loaded index. It is not a signature proving the index publisher's identity or upstream truth. The separate scientific verifier still parses frozen upstream records. Hosting the whole application in a single giant JSON would avoid some request races but inflate each load and obscure source partition boundaries. Use bounded edition/metric requests instead.

The real browser fault check appended whitespace to a valid school partition. Hash verification rejected it, disabled export and removed the prior prepared CSV. Restoring the original bytes and pressing Retry recovered the view. CSV checks also verified reversed-edition subtraction, source hashes, missing values and both 2010 GDP anchors.
