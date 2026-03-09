// Standalone developer-triggered build job.
// Mirrors main stages from build.Jenkinsfile while externalizing platform config.

properties([
    disableConcurrentBuilds(),
    buildDiscarder(logRotator(numToKeepStr: '50')),
    parameters([
        choice(name: 'PLATFORM', choices: ['Linux', 'Windows', 'Both', 'All'], description: 'Target platform mode'),
        choice(name: 'DISTRO', choices: ['ubuntu24.04', 'ubuntu25.10'], description: 'Linux distro (ignored for Windows)'),
        choice(name: 'BUILD_TYPE', choices: ['Release', 'Debug'], description: 'Build type'),
        booleanParam(name: 'RUN_TESTS', defaultValue: false, description: 'Run tests from build_xpum.py'),
        booleanParam(name: 'COLLECT_ARTIFACTS', defaultValue: true, description: 'Run artifact collection stage'),
        booleanParam(name: 'PACKAGE_ARTIFACTS', defaultValue: true, description: 'Run package stage'),
        booleanParam(name: 'UPLOAD_TO_ARTIFACTORY', defaultValue: false, description: 'Upload package artifacts'),
        booleanParam(name: 'ARCHIVE_PACKAGE', defaultValue: true, description: 'Archive package artifacts'),
        booleanParam(name: 'SIGN_WINDOWS_ARTIFACTS', defaultValue: false, description: 'Sign Windows artifacts (Windows only)'),
        string(name: 'GIT_REF', defaultValue: 'main', description: 'Branch, tag, or SHA to build'),
        string(name: 'CONFIG_RESOLVE_LABEL', defaultValue: '', description: '(Optional) Agent label used only to resolve ci/build-matrix.yml before dispatch'),
        string(name: 'WIN_DISTRO', defaultValue: 'server2022', description: 'Windows build target from ci/build-matrix.yml'),
        string(name: 'PROJECT', defaultValue: 'xpum', description: 'Project path token for Artifactory uploads'),
        string(name: 'ARTIFACTORY_URL', defaultValue: 'https://gfx-assets.fm.intel.com/artifactory', description: 'Artifactory root URL')
    ])
])

def MATRIX_FILE = 'ci/build-matrix.yml'
def REPO_URL = 'https://github.com/intel-innersource/libraries.compute.xpu-manager.xpum.git'
def ARTIFACTORY_CRED = 'artifactory-xpum'
def SIGN_CRED = 'sys_xpum_sign'
def RESOLVER_CLOUD = 'gar-oneapi-ci-hyc-windows-cluster'

def RESOLVER_POD_YAML = """
apiVersion: v1
kind: Pod
metadata:
  namespace: default
spec:
  nodeSelector:
    kubernetes.io/os: linux
  securityContext:
    runAsUser: 0
    fsGroup: 0
  containers:
    - name: jnlp
      image: 'amr-registry.caas.intel.com/oneapi-ci-hybrid-cloud/jenkins-inbound-agent:3256.v88a_f6e922152-jdk17'
    - name: resolver
      image: 'gar-registry.caas.intel.com/new-xpum/builder-conan:ubuntu'
      command: ['cat']
      tty: true
  volumes:
    - name: workspace-volume
      emptyDir: {}
  imagePullSecrets:
    - name: amr-registry
    - name: ger-registry-pre
""".stripIndent()

def cellId = { String os, String name ->
    // name = distroName or winTarget
    return "${os}_${name}_${params.BUILD_TYPE}"
}

def artifactDirFor = { String os, String name -> "artifacts_${cellId(os, name)}" }
def packageDirFor  = { String os, String name -> "packages_${cellId(os, name)}" }

def checkoutRef = {
    def remoteCfg = [url: REPO_URL]
    if (scm?.userRemoteConfigs && scm.userRemoteConfigs[0]?.credentialsId) {
        remoteCfg.credentialsId = scm.userRemoteConfigs[0].credentialsId
    }

    checkout([
        $class: 'GitSCM',
        branches: [[name: params.GIT_REF]],
        userRemoteConfigs: [remoteCfg],
        extensions: [
            [$class: 'CloneOption', shallow: false, noTags: false, depth: 0, honorRefspec: true],
            [$class: 'CleanBeforeCheckout']
        ]
    ])
}

def loadBuildMatrix = {
    if (!fileExists(MATRIX_FILE)) {
        error "Missing matrix config: ${MATRIX_FILE}"
    }
    return readYaml(file: MATRIX_FILE)
}

def inlinePodTemplatesIntoMatrix = { Map matrix ->
    if (!matrix?.linux) {
        return matrix
    }

    matrix.linux.each { String distro, def cfg ->
        if (!cfg) {
            return
        }

        def podTemplatePath = cfg.podTemplate
        if (!podTemplatePath) {
            return
        }

        if (!fileExists(podTemplatePath as String)) {
            error "Missing pod template file: ${podTemplatePath} (referenced by linux.${distro} in ${MATRIX_FILE})"
        }

        // Store template text in the matrix so linuxBuildFlow doesn't need workspace access pre-podTemplate().
        cfg.podYamlTemplate = readFile(podTemplatePath as String)
    }

    return matrix
}

def resolveBuildMatrix = {
    def matrix = null

    def resolveBlock = {
        checkoutRef()
        matrix = loadBuildMatrix()
        matrix = inlinePodTemplatesIntoMatrix(matrix as Map)
        cleanWs()
    }

    if (params.CONFIG_RESOLVE_LABEL?.trim()) {
        node(params.CONFIG_RESOLVE_LABEL.trim()) {
            resolveBlock()
        }
    } else {
        podTemplate(
            cloud: RESOLVER_CLOUD,
            yaml: RESOLVER_POD_YAML
        ) {
            node(POD_LABEL) {
                container('resolver') {
                    resolveBlock()
                }
            }
        }
    }

    if (!matrix) {
        error "Failed to resolve build matrix from ${MATRIX_FILE}"
    }
    return matrix
}

def computeTimestamp = {
    return new Date().format('yyyyMMdd_HHmmss', TimeZone.getTimeZone('UTC'))
}

def cellStage = { String os, String cell, String stageName, Closure body ->
    stage("${os} ${cell} - ${stageName}") {
        body()
    }
}

def linuxBuildFlow = { Map matrix, String distroName ->
    distroName = (distroName ?: (params.DISTRO as String) ?: null)
    if (!distroName) {
        error "Incorrect DISTRO (${params.DISTRO})"
    }

    def linuxCfg = matrix?.linux?.get(distroName)
    if (!linuxCfg) {
        error "Unsupported DISTRO='${distroName}'. Update ${MATRIX_FILE}."
    }

    String buildDir = "build_${params.BUILD_TYPE}"

    def artifactDir = artifactDirFor('Linux', distroName)
    def packageDir  = packageDirFor('Linux', distroName)

    String podYamlTemplate = linuxCfg.podYamlTemplate as String
    if (!podYamlTemplate) {
        error "Missing podYamlTemplate for linux.${distroName}. Ensure resolveBuildMatrix() hydrates pod templates."
    }

    String podYaml = podYamlTemplate.replace('dockerBuildImageName', linuxCfg.image as String)

    Map podOptions = [yaml: podYaml]
    if (linuxCfg.cloud) {
        podOptions.cloud = linuxCfg.cloud as String
    }

    podTemplate(podOptions) {
        node(POD_LABEL) {
            String containerName = (linuxCfg.containerName ?: 'xpum') as String
            container(containerName) {
                try {
                    cellStage('Linux', distroName, 'Checkout') {
                        checkoutRef()
                    }

                    cellStage('Linux', distroName, 'Build') {
                        def testFlag = params.RUN_TESTS ? '--run-tests' : ''
                        sh("""
                            cd jenkins/scripts
                            python3 build_xpum.py --build-type ${params.BUILD_TYPE} ${testFlag}
                        """.stripIndent())
                    }

                    if (params.COLLECT_ARTIFACTS) {
                        cellStage('Linux', distroName, 'Collect Artifacts') {
                            sh("""
                                cd jenkins/scripts
                                python3 collect_artifacts.py --platform Linux --build-type ${params.BUILD_TYPE} \\
                                                             --source-dir ../../${buildDir} \\
                                                             --output-dir ../../${artifactDir}
                            """.stripIndent())
                        }
                    }

                    if (params.PACKAGE_ARTIFACTS) {
                        cellStage('Linux', distroName, 'Package Artifacts') {
                            sh("""
                                cd jenkins/scripts
                                COMMIT=\$(git rev-parse HEAD)
                                TIMESTAMP=${computeTimestamp()}
                                python3 package_artifacts.py --artifact-dir ../../${artifactDir} \\
                                                             --output-dir ../../${packageDir} \\
                                                             --commit \$COMMIT \\
                                                             --timestamp \$TIMESTAMP \\
                                                             --platform Linux
                            """.stripIndent())
                        }
                    }

                    if (params.UPLOAD_TO_ARTIFACTORY) {
                        cellStage('Linux', distroName, 'Upload to Artifactory') {
                            withCredentials([usernamePassword(credentialsId: ARTIFACTORY_CRED, usernameVariable: 'ARTIFACTORY_USER', passwordVariable: 'ARTIFACTORY_PASSWORD')]) {
                                sh("""
                                    set -e
                                    python3 jenkins/scripts/gta_asset.py push \\
                                        --asset-path "gfx-xpu-manager/test/${params.PROJECT}/${env.BUILD_NUMBER}/Linux" \\
                                        --asset-name "${distroName}" \\
                                        --asset-version "${params.BUILD_TYPE}" \\
                                        --asset-src "${packageDir}" \\
                                        --root-url "${params.ARTIFACTORY_URL}" \\
                                        --no-archive
                                """.stripIndent())
                            }
                        }
                    }

                } finally {
                    cellStage('Linux', distroName, 'Archive build') {
                        archiveArtifacts allowEmptyArchive: true, artifacts: [
                            "${packageDir}/*.tar.gz",
                            "${packageDir}/*.zip"
                        ].join(',')
                    }
                    cellStage('Linux', distroName, 'Archive logs') {
                        archiveArtifacts allowEmptyArchive: true, artifacts: [
                            '**/meson-logs/**',
                            '**/build*/meson-logs/**',
                            '**/*.log'
                        ].join(',')
                    }
                    cleanWs()
                }
            }
        }
    }
}

def windowsBuildFlow = { Map matrix, String winTarget ->
    winTarget = (winTarget ?: (params.WIN_DISTRO as String) ?: null)
    if (!winTarget) {
        error "Incorrect WIN_DISTRO (${params.WIN_DISTRO})"
    }

    def windowsCfg = matrix?.windows?.get(winTarget)
    if (!windowsCfg) {
        error "Unsupported WIN_DISTRO='${winTarget}'. Update ${MATRIX_FILE}."
    }

    String buildDir = "build_${params.BUILD_TYPE}"

    String agentLabel = windowsCfg.agentLabel as String
    if (!agentLabel?.trim()) {
        error "Missing windows.${winTarget}.agentLabel in ${MATRIX_FILE}"
    }

    node(agentLabel) {
        // Prevent parallel branches (Both/All) from sharing the same workspace on the same node.
        ws("${env.WORKSPACE}@${winTarget}") {
            try {
                cellStage('Windows', winTarget, 'Checkout') {
                    cleanWs()
                    checkoutRef()
                }

                String artifactDir = artifactDirFor('Windows', winTarget)
                String packageDir = packageDirFor('Windows', winTarget)

                String commit = powershell(
                    returnStdout: true,
                    script: "git rev-parse HEAD"
                ).trim()
                String timestamp = computeTimestamp()

                cellStage('Windows', winTarget, 'Build') {
                    def testFlag = params.RUN_TESTS ? '--run-tests' : ''
                    powershell("""
                        Set-StrictMode -Version Latest
                        \$ErrorActionPreference = "Stop"

                        python jenkins/scripts/build_xpum.py --build-type ${params.BUILD_TYPE} ${testFlag}
                    """.stripIndent())
                }

                if (params.COLLECT_ARTIFACTS) {
                    cellStage('Windows', winTarget, 'Collect Artifacts') {
                        powershell("""
                            Set-StrictMode -Version Latest
                            \$ErrorActionPreference = "Stop"

                            python jenkins/scripts/collect_artifacts.py `
                                --platform Windows `
                                --build-type ${params.BUILD_TYPE} `
                                --source-dir ${buildDir} `
                                --output-dir ${artifactDir}
                        """.stripIndent())
                    }
                }

                if (params.SIGN_WINDOWS_ARTIFACTS) {
                    cellStage('Windows', winTarget, 'Sign Artifacts') {
                        withCredentials([
                            usernamePassword(
                                credentialsId: SIGN_CRED,
                                usernameVariable: 'SIGN_USER',
                                passwordVariable: 'SIGN_PASSWORD'
                            )
                        ]) {
                            powershell("""
                                Set-StrictMode -Version Latest
                                \$ErrorActionPreference = "Stop"

                                python jenkins/scripts/sign_artifacts.py `
                                    --platform Windows `
                                    --artifact-dir ${artifactDir} `
                                    --username \$env:SIGN_USER `
                                    --password \$env:SIGN_PASSWORD
                            """.stripIndent())
                        }
                    }
                }

                if (params.PACKAGE_ARTIFACTS) {
                    cellStage('Windows', winTarget, 'Package Artifacts') {
                        powershell("""
                            Set-StrictMode -Version Latest
                            \$ErrorActionPreference = "Stop"

                            python jenkins/scripts/package_artifacts.py `
                                --platform Windows `
                                --artifact-dir ${artifactDir} `
                                --output-dir ${packageDir} `
                                --commit ${commit} `
                                --timestamp ${timestamp}
                        """.stripIndent())
                    }
                }

                if (params.UPLOAD_TO_ARTIFACTORY) {
                    cellStage('Windows', winTarget, 'Upload to Artifactory') {
                        withCredentials([
                            usernamePassword(
                                credentialsId: ARTIFACTORY_CRED,
                                usernameVariable: 'ARTIFACTORY_USER',
                                passwordVariable: 'ARTIFACTORY_PASSWORD'
                            )
                        ]) {
                            powershell("""
                                Set-StrictMode -Version Latest
                                \$ErrorActionPreference = "Stop"

                                python jenkins/scripts/gta_asset.py push `
                                    --asset-path "gfx-xpu-manager/test/${params.PROJECT}/${env.BUILD_NUMBER}/Windows" `
                                    --asset-name "${winTarget}" `
                                    --asset-version "${params.BUILD_TYPE}" `
                                    --asset-src "${packageDir}" `
                                    --root-url "${params.ARTIFACTORY_URL}" `
                                    --no-archive
                            """.stripIndent())
                        }
                    }
                }
            } finally {
                cellStage('Windows', winTarget, 'Archive logs') {
                    archiveArtifacts allowEmptyArchive: true, artifacts: [
                        '**/meson-logs/**',
                        '**/build*/meson-logs/**',
                        '**/*.log'
                    ].join(',')
                }
                cleanWs()
            }
        }
    }
}

timeout(time: 90, unit: 'MINUTES') {
    stage('Init') {
        currentBuild.displayName = "#${env.BUILD_NUMBER} [${params.PLATFORM}-${params.BUILD_TYPE}-${params.GIT_REF}]"
        currentBuild.description = "Platform=${params.PLATFORM}, BuildType=${params.BUILD_TYPE}, Tests=${params.RUN_TESTS}, Distro=${params.DISTRO}"
        echo "=== Standalone Build Configuration ==="
        echo "Platform: ${params.PLATFORM}"
        echo "Distro: ${params.DISTRO}"
        echo "Windows target: ${params.WIN_DISTRO}"
        echo "Build type: ${params.BUILD_TYPE}"
        echo "Run tests: ${params.RUN_TESTS}"
        echo "Collect artifacts: ${params.COLLECT_ARTIFACTS}"
        echo "Package artifacts: ${params.PACKAGE_ARTIFACTS}"
        echo "Sign Windows artifacts: ${params.SIGN_WINDOWS_ARTIFACTS}"
        echo "Upload to Artifactory: ${params.UPLOAD_TO_ARTIFACTORY}"
        echo "Git ref: ${params.GIT_REF}"
        echo "======================================"
    }

    stage('Dispatch') {
        def matrix = resolveBuildMatrix()
        if (params.PLATFORM == 'Linux') {
            linuxBuildFlow(matrix, params.DISTRO as String)
        } else if (params.PLATFORM == 'Windows') {
            windowsBuildFlow(matrix, params.WIN_DISTRO as String)
        } else if (params.PLATFORM == 'Both') {
            parallel(
                failFast: true,
                Linux: { linuxBuildFlow(matrix, params.DISTRO as String) },
                Windows: { windowsBuildFlow(matrix, params.WIN_DISTRO as String) }
            )
        } else if (params.PLATFORM == 'All') {
            def branches = [:]
            matrix?.linux?.keySet()?.sort()?.each { distro ->
                String distroName = distro as String
                branches["Linux-${distroName}"] = { linuxBuildFlow(matrix, distroName) }
            }
            matrix?.windows?.keySet()?.sort()?.each { target ->
                String winTarget = target as String
                branches["Windows-${winTarget}"] = { windowsBuildFlow(matrix, winTarget) }
            }

            if (branches.isEmpty()) {
                error "No build targets found in ${MATRIX_FILE}"
            }

            branches.failFast = true
            parallel branches
        } else {
            error "Unsupported PLATFORM='${params.PLATFORM}'"
        }
    }
}