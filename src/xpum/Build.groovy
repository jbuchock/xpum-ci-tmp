package xpum

/**
 * Build — product-repo checkout, Conan/Meson build, artifact collection, and packaging.
 *
 * Instantiate with the pipeline steps context:
 *
 *   def build = new xpum.Build(this)
 *
 * All methods assume they are called from inside an appropriate node/container.
 * Agent/pod allocation is the caller's (Jenkinsfile) responsibility.
 */
class Build implements Serializable {

    private final def steps

    Build(def steps) {
        this.steps = steps
    }

    // -----------------------------------------------------------------------
    // Checkout
    // -----------------------------------------------------------------------

    /**
     * Check out the product repo at the given ref.
     * Uses the github-app-xpum credential from the Jenkins credential store.
     */
    void checkout(String repoUrl, String gitRef) {
        steps.checkout([
            $class:            'GitSCM',
            branches:          [[name: gitRef]],
            userRemoteConfigs: [[url: repoUrl, credentialsId: 'git']],
            extensions:        [
                [$class: 'CloneOption',        shallow: false, noTags: false, depth: 0],
                [$class: 'CleanBeforeCheckout']
            ]
        ])
    }

    // -----------------------------------------------------------------------
    // Build
    // -----------------------------------------------------------------------

    /** Run build_xpum.py on Linux. */
    void buildLinux(String buildType) {
        steps.sh("python3 jenkins/scripts/build_xpum.py --build-type ${buildType}")
    }

    /** Run build_xpum.py on Windows. */
    void buildWindows(String buildType) {
        steps.powershell("""
            Set-StrictMode -Version Latest
            \$ErrorActionPreference = "Stop"

            python jenkins/scripts/build_xpum.py --build-type ${buildType}
        """.stripIndent())
    }

    // -----------------------------------------------------------------------
    // Collect artifacts
    // -----------------------------------------------------------------------

    /**
     * Run collect_artifacts.py.
     * Works on both Linux (sh) and Windows (powershell) based on isUnix().
     *
     * @param platform   'Linux' or 'Windows'
     * @param buildType  e.g. 'release' or 'debug'
     * @param sourceDir  Directory containing the build outputs (relative to workspace root)
     * @param outputDir  Staging directory for collected artifacts
     */
    void collectArtifacts(String platform, String buildType, String sourceDir, String outputDir) {
        if (steps.isUnix()) {
            steps.sh("""
                python3 jenkins/scripts/collect_artifacts.py \\
                    --platform ${platform} \\
                    --build-type ${buildType} \\
                    --source-dir ${sourceDir} \\
                    --output-dir ${outputDir}
            """.stripIndent())
        } else {
            steps.powershell("""
                Set-StrictMode -Version Latest
                \$ErrorActionPreference = "Stop"

                python jenkins/scripts/collect_artifacts.py `
                    --platform ${platform} `
                    --build-type ${buildType} `
                    --source-dir ${sourceDir} `
                    --output-dir ${outputDir}
            """.stripIndent())
        }
    }

    // -----------------------------------------------------------------------
    // Package artifacts
    // -----------------------------------------------------------------------

    /**
     * Run package_artifacts.py.
     * Works on both Linux (sh) and Windows (powershell) based on isUnix().
     *
     * @param platform    'Linux' or 'Windows'
     * @param artifactDir Directory produced by collectArtifacts()
     * @param outputDir   Destination for the final package (tarball / zip / installer)
     * @param commit      Product-repo commit SHA (embedded in package metadata)
     * @param timestamp   UTC build timestamp string, e.g. '20260309_143000'
     */
    void packageArtifacts(String platform, String artifactDir, String outputDir,
                          String commit, String timestamp) {
        if (steps.isUnix()) {
            steps.sh("""
                python3 jenkins/scripts/package_artifacts.py \\
                    --platform ${platform} \\
                    --artifact-dir ${artifactDir} \\
                    --output-dir ${outputDir} \\
                    --commit ${commit} \\
                    --timestamp ${timestamp}
            """.stripIndent())
        } else {
            steps.powershell("""
                Set-StrictMode -Version Latest
                \$ErrorActionPreference = "Stop"

                python jenkins/scripts/package_artifacts.py `
                    --platform ${platform} `
                    --artifact-dir ${artifactDir} `
                    --output-dir ${outputDir} `
                    --commit ${commit} `
                    --timestamp ${timestamp}
            """.stripIndent())
        }
    }
}
