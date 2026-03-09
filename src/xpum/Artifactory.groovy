package xpum

/**
 * Artifactory — gta-asset upload wrappers.
 *
 * Only the scratch path is available here.  The official release path
 * (uploadOfficial) is implemented in post-merge only and requires
 * folder-scoped credentials in xpum/20_mainline/.
 *
 * Instantiate with the pipeline steps context:
 *
 *   def art = new xpum.Artifactory(this)
 *   art.pushToArtifactory(credentialsId, assetPath, sourceDir)
 */
class Artifactory implements Serializable {

    static final String ROOT_URL = 'https://gfx-assets.fm.intel.com/artifactory'

    private final def steps

    Artifactory(def steps) {
        this.steps = steps
    }

    /**
     * Upload a directory of packaged artifacts to the Artifactory scratch path.
     *
     * The credential must be a username/password type stored in the Jenkins
     * credential store — never passed through pipeline parameters (Core Principle 3).
     *
     * @param credentialsId  Jenkins credential ID (e.g. 'artifactory-xpum-scratch')
     * @param assetPath      Repository-relative parent path,
     *                       e.g. 'xpum-scratch/dev/42/Linux'
     * @param assetName      Asset name within the path (distro or Windows target),
     *                       e.g. 'ubuntu24.04' or 'server2022'
     * @param assetVersion   Build type string passed as asset version,
     *                       e.g. 'Release' or 'Debug'
     * @param sourceDir      Local workspace directory containing the package files
     */
    void pushToArtifactory(String credentialsId, String assetPath, String assetName,
                       String assetVersion, String sourceDir) {
        steps.withCredentials([steps.usernamePassword(
            credentialsId: credentialsId,
            usernameVariable: 'ARTIFACTORY_USER',
            passwordVariable: 'ARTIFACTORY_PASSWORD'
        )]) {
            if (steps.isUnix()) {
                steps.sh("""
                    set -e
                    python3 jenkins/scripts/gta_asset.py push \\
                        --asset-path "${assetPath}" \\
                        --asset-name "${assetName}" \\
                        --asset-version "${assetVersion}" \\
                        --asset-src "${sourceDir}" \\
                        --root-url "${ROOT_URL}" \\
                        --no-archive
                """.stripIndent())
            } else {
                steps.powershell("""
                    Set-StrictMode -Version Latest
                    \$ErrorActionPreference = "Stop"

                    python jenkins/scripts/gta_asset.py push `
                        --asset-path "${assetPath}" `
                        --asset-name "${assetName}" `
                        --asset-version "${assetVersion}" `
                        --asset-src "${sourceDir}" `
                        --root-url "${ROOT_URL}" `
                        --no-archive
                """.stripIndent())
            }
        }
    }
}
