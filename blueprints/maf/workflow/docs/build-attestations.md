# Build-attestation preflight

`scripts/verify_build_attestations.py` is an **advisory**, online check of
three immutable OCI image attestations. It does not deploy, authorize a
release, or establish which image is running. It works in a generated project
without the blueprint repository.

An independent authority must administer the policy, approved source and
signer, trusted verifier and `gh` binary, runner, registry access, and trust
roots outside the candidate change. This script only rejects a policy path
inside the project or an enclosing Git checkout; it does not authenticate the
file, its owner, or its administration. An external path alone does not
establish independence. Do not put credentials or private deployment details
in the repository, policy examples, or public logs.

## Policy and invocation

Use Python 3.12 and GitHub CLI 2.97.0 or later within major version 2. The
check was exercised with `gh` 2.103.3. The operator must arrange authenticated
access to the source repository's GitHub attestations and to each registry
through their approved mechanisms. It uses `github.com` and the CLI's normal
online trust configuration; GitHub Enterprise Server and offline verification
are not supported by this script.

The following is a **synthetic, nonfunctional** policy illustrating its
required shape; an independent authority supplies real values in an absolute
file outside the project. Each image is a fully qualified OCI name followed
by its exact lowercase SHA-256 manifest or index digest. The three
name-and-digest subjects must be distinct. Do not substitute tags.

```json
{
  "schema_version": "1",
  "source": {
    "repository": "example-owner/example-source",
    "repository_id": "1234",
    "owner_id": "42",
    "ref": "refs/heads/main",
    "revision": "1111111111111111111111111111111111111111"
  },
  "subjects": {
    "api": {
      "image": "registry.example.invalid/team/api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "signer_identity": "https://github.com/example-builder/builds/.github/workflows/publish.yml@refs/heads/main",
      "signer_revision": "2222222222222222222222222222222222222222"
    },
    "web": {
      "image": "registry.example.invalid/team/web@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "signer_identity": "https://github.com/example-builder/builds/.github/workflows/publish.yml@refs/heads/main",
      "signer_revision": "2222222222222222222222222222222222222222"
    },
    "foundry": {
      "image": "registry.example.invalid/team/foundry@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "signer_identity": "https://github.com/example-builder/builds/.github/workflows/publish.yml@refs/heads/main",
      "signer_revision": "2222222222222222222222222222222222222222"
    }
  }
}
```

`repository_id` and `owner_id` are independently pinned GitHub numeric IDs
encoded as strings. `revision` is the exact reviewed 40-character lowercase
commit. `ref` must be a full branch or tag ref, not a PR merge ref.
`signer_identity` is the certificate's exact GitHub Actions workflow identity,
including its full branch/tag ref or 40-character reusable-workflow commit.
`signer_revision` pins the workflow's commit independently; when the identity
uses a commit, the two must match.

```text
python scripts/verify_build_attestations.py --policy <absolute-external-policy.json>
```

For each subject, the script delegates cryptographic verification to `gh
attestation verify` and requires the exact issuer, certificate identity, signer
and source commits/ref, GitHub-hosted runner, and SLSA v1 predicate. It then
checks the same verified result's repository and owner IDs, in-toto subject
name and digest, verified timestamps, and standard GitHub Actions build
predicate: source, dependency commit, builder, runner, and invocation must
agree with the certificate. It rejects missing, malformed, duplicate or
ambiguous records, including more than one verified attestation or more than
one subject in an attestation. These constraints may reject otherwise valid
custom or multi-subject attestations.

On success, the JSON output says `build_attestations: verified`,
`deployment_provenance: unverified`, and `release_authorized: false`; exit 0 is
**not** a release gate. It also contains the policy's source revision, so
handle output according to the source's sensitivity. Failures are nonzero and
do not print registry names or `gh` stderr. Diagnose authorization and
attestations privately rather than copying credentials or raw output to logs.

## What this cannot establish

- The GitHub event SHA in the certificate and predicate is not necessarily the
  checked-out SHA. A separately governed, reviewed builder must guarantee
  event SHA = actual checkout = reviewed commit, derive each attested digest
  from its own build output, and bind generated contexts, build arguments,
  base images and dependencies. A builder-controlled signature or caller-supplied
  digest alone cannot establish that guarantee.
- The repository's current ACR local-context builds and Foundry source ZIP
  `remote_build` do not supply this verified source-to-image binding. The
  ZIP hash is not a built image digest. Foundry supports a prebuilt
  digest-pinned ACR image, but that path, runtime compatibility, pull access,
  and existing-session behavior have not been verified here.
- An independently governed observer must authenticate fresh, scoped ACA
  revision/traffic/image and Foundry version/route/image/identity observations,
  with nonce, expiry and controlled deployment concurrency. A configured
  digest is not a provider-signed measurement of the running image. The
  preflight does not inspect Azure, verify a signed observation, distinguish
  an index from the selected platform image, or prevent concurrent changes.
- The failure-injection workflow's pre-OIDC hard stop remains in place. No
  trusted builder, independent policy or observer, protected environment,
  target artifact, isolation, live deployment, or rollout is established by
  this preflight. Existing authorization and PostgreSQL firewall rules remain
  unchanged.

See GitHub's [attestation guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
and [reusable-workflow guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/increase-security-rating).
