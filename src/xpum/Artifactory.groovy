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
 *   art.uploadScratch(credentialsId, assetPath, sourceDir)
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
     * @param assetPath      Repository-relative destination path,
     *                       e.g. 'xpum-scratch/dev/42/Linux/ubuntu24.04/release'
     * @param sourceDir      Local workspace directory containing the package files
     */
    void uploadScratch(String credentialsId, String assetPath, String sourceDir) {
        steps.withCredentials([steps.usernamePassword(
            credentialsId: credentialsId,
            usernameVariable: 'ART_USER',
            passwordVariable: 'ART_PASSWORD'
        )]) {
            if (steps.isUnix()) {
                steps.sh("""
                    python3 jenkins/scripts/gta_asset.py push \\
                        --asset-path "${assetPath}" \\
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
                        --asset-src "${sourceDir}" `
                        --root-url "${ROOT_URL}" `
                        --no-archive
                """.stripIndent())
            }
        }
    }
}
