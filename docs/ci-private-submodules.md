# CI Private Submodules

If a package created from this template uses private GitHub submodules, the
default [`GITHUB_TOKEN`](https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication)
may not be able to clone them in GitHub Actions.

Use a [GitHub App](https://docs.github.com/en/apps/overview) token pattern for
private submodules. The
[`actions/create-github-app-token`](https://github.com/actions/create-github-app-token)
action creates a short-lived installation access token that can be scoped to the
parent repo and the private submodule repos:

```yaml
- name: Create GitHub App token
  id: app-token
  uses: actions/create-github-app-token@v3
  with:
    client-id: ${{ vars.CI_APP_CLIENT_ID }}
    private-key: ${{ secrets.CI_APP_PRIVATE_KEY }}
    owner: your-org
    repositories: |
      your_repo
      private_submodule_repo
    permission-contents: read

- name: Check out repository
  uses: actions/checkout@v6
  with:
    token: ${{ steps.app-token.outputs.token }}
    submodules: recursive
    persist-credentials: false
```

Required repository settings:

- Variable: `CI_APP_CLIENT_ID`
- Secret: `CI_APP_PRIVATE_KEY`

Create these under the repository's
[Actions variables and secrets settings](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-variables)
and
[Actions secrets settings](https://docs.github.com/en/actions/how-tos/security-for-github-actions/security-guides/using-secrets-in-github-actions).

The GitHub App must be installed on the parent repo and each private submodule
repo listed under `repositories`. See GitHub's docs for
[installing your own GitHub App](https://docs.github.com/en/apps/using-github-apps/installing-your-own-github-app).

Replace the variable and secret names in the YAML with whatever naming
convention your repository uses.

`actions/create-github-app-token` still accepts the older `app-id` input, but
the upstream action now recommends `client-id`. Prefer `client-id` in new
workflows to avoid deprecation/legacy-input warnings. GitHub documents where to
find a GitHub App's client ID in the
[GitHub App settings](https://docs.github.com/en/apps/maintaining-github-apps/modifying-a-github-app).

Symptoms when this is missing:

- PR checks stay queued and then fail during checkout.
- [`actions/checkout`](https://github.com/actions/checkout) reports that it
  cannot clone a private submodule.
- SSH submodule URLs like `git@github.com:org/private_repo.git` fail in CI even
  though they work locally.

When adapting the template, either avoid private submodules in CI or add the
token step before every `actions/checkout` step that uses `submodules:
recursive`.
