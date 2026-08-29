# Pinned Token Standard interfaces

These interface-only DARs come from the Splice `0.6.8` LocalNet release used by
this toolkit. They compile `MandateUsage.Charge` against Token Standard V1 while
leaving the concrete token implementation to the deployed registry/issuer.

They are checked in deliberately so builds do not depend on a machine-specific
LocalNet extraction directory or an unpinned download:

| DAR | SHA-256 |
|---|---|
| `splice-api-token-metadata-v1-1.0.0.dar` | `455eb160cb5abd4ae9918a6fbb9dad471f721adda39f0e5c76feef08d05637fc` |
| `splice-api-token-holding-v1-1.0.0.dar` | `ef75f8eb41a65810221784fdb78bb9dfac7cb22245aba14fa7cb7f69c34e0175` |
| `splice-api-token-transfer-instruction-v1-1.0.0.dar` | `e4c73aa7ae73fb2fc330b938ffb99f568792321640ba4b9472902aa8d742c994` |

Verify the vendored files from this directory with:

```bash
shasum -a 256 -c SHA256SUMS
```

When LocalNet is upgraded, replace all three DARs together, update the hashes,
and rerun both the Daml suite and the opt-in real LocalNet integration test.
