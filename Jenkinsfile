// CI on the self-hosted forge: a second lap over everything the local hooks and
// the GitHub workflows run. Every stage CALLS the same script they call; nothing
// is reimplemented here.
//
//   gate                     local hook              workflow                    stage here
//   tests                    (none)                  ci.yml / test               project gates pyX.Y
//   English: tracked files   hooks/pre-commit        ci.yml / self, smoke        project gates pyX.Y, smoke
//   no strict extra          (none)                  ci.yml / no-strict-extra    no strict extra
//   shipped YAML parses      (none)                  ci.yml / yaml               yaml
//   English: commits         hooks/commit-msg        ci.yml / self               lang: commit messages
//   English: PR text         (none)                  lang-pr.yml                 lang: PR title and description
//   links                    hooks/pre-push.d        darnlink-gate.yml           darnlink-gate
//   private references       hooks/pre-push          privacy-gate.yml            not here: a private job on the CI server runs tools/privacy_gate.sh
//   secrets in the diff      (private tooling)       (none)                      secret-scan
//   repo_policy.yaml         (none)                  (none)                      repo_policy.yaml
//   the shipped action       (none)                  ci.yml / self (uses: ./)    not ported: a GitHub action can only run on GitHub
//   English: issues          (none)                  lang-issue.yml              not ported: fired by an issue, not a commit
//   release                  (none)                  publish.yml                 not ported: a release job, not a check
//
// No host names, URLs or secrets live in this file: they come from the CI server
// (SECRET_SCAN_URL and the credential 'scm-api-token').

def PYTHONS = ['3.10', '3.11', '3.12', '3.13']

// tools/check.sh is what the workflows run. uv honours UV_PYTHON, so the same
// script covers the whole Python matrix.
def localGates(String py, boolean unix) {
  withEnv(["UV_PYTHON=${py}", "UV_PROJECT_ENVIRONMENT=.venv-${py}"]) {
    // On Windows `bash` is the one Git for Windows ships; it is not on PATH by default.
    if (unix) { sh 'bash tools/check.sh' } else { bat '"%ProgramFiles%\\Git\\bin\\bash.exe" tools/check.sh' }
  }
}

pipeline {
  agent none
  options { timestamps(); disableConcurrentBuilds(); timeout(time: 90, unit: 'MINUTES') }
  stages {
    stage('checks') {
      parallel {

        stage('linux') {
          agent { label 'linux' }
          environment {
            PATH = "${HOME}/.local/bin:${PATH}"
          }
          stages {
            stage('repo_policy.yaml') {
              steps { sh 'python3 tools/repo_policy_check.py' }
            }
            stage('project gates') {
              steps { script { PYTHONS.each { py -> stage("project gates py${py}") { localGates(py, true) } } } }
            }
            stage('pull request context') {
              when { changeRequest() }
              steps {
                withCredentials([
                  usernamePassword(credentialsId: 'scm-api-token', usernameVariable: 'API_USER', passwordVariable: 'API_TOKEN'),
                  gitUsernamePassword(credentialsId: 'scm-api-token')
                ]) {
                  sh '''
                    set -eu
                    # A PR checkout only brings the PR ref: fetch the base explicitly.
                    git fetch --quiet origin "+refs/heads/${CHANGE_TARGET}:refs/remotes/origin/${CHANGE_TARGET}"
                    # The API address is derived from CHANGE_URL; the token stays in the environment.
                    { set +x; } 2>/dev/null
                    PR_TEXT_FILE="${WORKSPACE_TMP}/pr.txt" python3 tools/pr_text.py
                    set -x
                  '''
                }
              }
            }
            stage('lang: commit messages') {
              when { changeRequest() }
              steps { sh 'bash tools/lang_commits.sh "origin/${CHANGE_TARGET}" HEAD' }
            }
            stage('lang: PR title and description') {
              when { changeRequest() }
              steps { sh 'bash tools/lang_gate.sh pr-text "${WORKSPACE_TMP}/pr.txt"' }
            }
            stage('no strict extra') {
              steps { sh 'UV_PROJECT_ENVIRONMENT=.venv-no-strict bash tools/check.sh no-strict' }
            }
            stage('yaml') {
              steps { sh 'uv run --no-project --with pyyaml python3 tools/yaml_check.py' }
            }
            stage('darnlink-gate') {
              steps { sh 'bash tools/darnlink_gate.sh' }
            }
            stage('smoke') {
              steps { sh 'uvx --from . darnlang check --ext all' }
            }
            stage('secret-scan') {
              steps {
                withCredentials([
                  usernamePassword(credentialsId: 'scm-api-token', usernameVariable: 'API_USER', passwordVariable: 'API_TOKEN')
                ]) {
                  sh '''
                    set -eu
                    : "${SECRET_SCAN_URL:?SECRET_SCAN_URL is not set on the CI server. Failing closed.}"
                    { set +x; } 2>/dev/null
                    printf 'header = "Authorization: token %s"\\n' "${API_TOKEN}" | curl -fsSL --config - \
                      "${SECRET_SCAN_URL}" -o "${WORKSPACE_TMP}/secret-scan"
                    set -x
                    # Only what the branch adds is judged; on a branch build, the last commit.
                    if [ -n "${CHANGE_TARGET:-}" ]; then base="origin/${CHANGE_TARGET}"; else base="HEAD~1"; fi
                    python3 "${WORKSPACE_TMP}/secret-scan" --against "$base"
                  '''
                }
              }
            }
          }
        }

        stage('windows') {
          agent { label 'windows' }
          environment { PATH = "${env.USERPROFILE}\\.local\\bin;${env.PATH}" }
          stages {
            // Same job as astral-sh/setup-uv in the workflows: a per-user install, only if missing,
            // pinned to the version the first green Windows run used.
            stage('setup uv') {
              steps {
                powershell '''
                  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
                    Invoke-RestMethod https://astral.sh/uv/0.12.17/install.ps1 | Invoke-Expression
                  }
                  uv --version
                '''
              }
            }
            stage('project gates') {
              steps { script { PYTHONS.each { py -> stage("project gates py${py} (windows)") { localGates(py, false) } } } }
            }
            stage('smoke') {
              steps { bat 'uvx --from . darnlang check --ext all' }
            }
          }
        }

      }
    }
  }
}
