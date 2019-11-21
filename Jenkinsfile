String cron_format = env.BRANCH_NAME == 'master' ? '00 10 * * *' : ''

def terraformInit(deployment) {
    dir("terraform/${deployment}") {
        sh "pwd"
        sh "ls -al"
        sh "terraform init -backend-config='bucket=jenkins-terraform' -backend-config='prefix=state/hsbc-6320774-enforcer-${deployment}'"
    }
}

def terraformValidate(deployment) {
    dir("terraform/${deployment}") {
        sh "terraform validate -no-color"
    }
}

def terraformPlan(deployment, unique_name) {
    dir("terraform/${deployment}") {
        sh "terraform plan -refresh=true -no-color -out /tmp/tf-${unique_name}.plan -lock=true -lock-timeout=5m"
        def tf_plan = sh (
            script: "terraform show -no-color /tmp/tf-${unique_name}.plan",
            returnStdout: true
        ).trim()
        def tf_plan_split = tf_plan.split('\n')
        def tf_plan_hash = java.security.MessageDigest.getInstance('SHA-256').digest(tf_plan.getBytes('UTF-8')).encodeBase64().toString()
        // Loop through plan output
        def added_resources = "| Type | Name |\n| --- | --- |"
        def changed_resources = "| Type | Name |\n| --- | --- |"
        def deleted_resources = "| Type | Name |\n| --- | --- |"
        def replaced_resources = "| Type | Name |\n| --- | --- |"
        tf_plan_split.each { line ->
            // Trim line
            line = line.trim()
            // Determine if this is an added, changed or deleted resource line
            if (line.startsWith('+ ')) {
                def resource = line.split(' ')[1].split('\\.')
                def resource_type = resource[0]
                def resource_name = resource[1]
                if (resource_type == "module") {
                    resource_type = resource[2]
                    resource_name = resource[3]
                }
                added_resources += "\n| ${resource_type} | ${resource_name} |"
            } else if (line.startsWith('~ ')) {
                def resource = line.split(' ')[1].split('\\.')
                def resource_type = resource[0]
                def resource_name = resource[1]
                if (resource_type == "module") {
                    resource_type = resource[2]
                    resource_name = resource[3]
                }
                changed_resources += "\n| ${resource_type} | ${resource_name} |"
            } else if (line.startsWith('- ')) {
                def resource = line.split(' ')[1].split('\\.')
                def resource_type = resource[0]
                def resource_name = resource[1]
                if (resource_type == "module") {
                    resource_type = resource[2]
                    resource_name = resource[3]
                }
                deleted_resources += "\n| ${resource_type} | ${resource_name} |"
            } else if (line.startsWith('-/+ ')) {
                def resource = line.split(' ')[1].split('\\.')
                def resource_type = resource[0]
                def resource_name = resource[1]
                if (resource_type == "module") {
                    resource_type = resource[2]
                    resource_name = resource[3]
                }
                replaced_resources += "\n| ${resource_type} | ${resource_name} |"
            }
        }
        def pr_comment = "The following resources will be affected by this deployment:\n\n**Added**\n\n${added_resources}\n\n**Changed**\n\n${changed_resources}\n\n**Deleted**\n\n${deleted_resources}\n\n**Replaced**\n\n${replaced_resources}\n\nTo apply these changes, approve the PR and then add the comment **/apply**."
        // Check to see if this a apply request
        if (build_trigger == 'ISSUE_COMMENT_APPLY') {
            // Copy hash from GCS
            sh "gsutil cp gs://jenkins-terraform/plan/tf-${unique_name}.hash /tmp/"
            // Check the hashes
            def previous_tf_plan_hash = sh (
                script: "cat /tmp/tf-${unique_name}.hash",
                returnStdout: true
            ).trim()
            if (previous_tf_plan_hash != tf_plan_hash) {
                pullRequest.comment("**The state has changed since this PR was opened**\n\n${pr_comment}")
                writeFile file: "/tmp/tf-${unique_name}.hash", text: tf_plan_hash
                sh "gsutil cp /tmp/tf-${unique_name}.* gs://jenkins-terraform/plan/"
                error 'The state has changed since this PR was opened'
            }
        } else {
            writeFile file: "/tmp/tf-${unique_name}.hash", text: tf_plan_hash
            pullRequest.comment(pr_comment)
        }
        
        // Copy plan and hash to GCS
        sh "gsutil cp /tmp/tf-${unique_name}.* gs://jenkins-terraform/plan/"
    }
}

def terraformApply(deployment, unique_name) {
    dir("terraform/${deployment}") {
        // Copy plan and hash from GCS
        sh "gsutil cp gs://jenkins-terraform/plan/tf-${unique_name}.* /tmp/"
        def tf_plan = sh (
            script: "terraform show -no-color /tmp/tf-${unique_name}.plan",
            returnStdout: true
        ).trim()
        // Apply Terraform
        sh "terraform apply -no-color /tmp/tf-${unique_name}.plan"
        // Delete plan and hash from local filesystem & GCS
        sh "rm -f /tmp/tf-${unique_name}.*"
        sh "gsutil rm gs://jenkins-terraform/plan/tf-${unique_name}.*"
        // Comment
        pullRequest.comment("Terraform Applied Successfully.")
        
    }
}

pipeline {
    agent any  
 
    options {
        buildDiscarder logRotator(artifactDaysToKeepStr: '', artifactNumToKeepStr: '', daysToKeepStr: '7', numToKeepStr: '5')
    }

    environment {
        build_trigger = 'OTHER'
        configs_changed = 'NO'
        def unique_name = "hsbc-6320774-enforcer-${deployment}-${env.CHANGE_ID}"
        def component_name = "ocean-ip-enforcer"
    }
 
    triggers {
        cron(cron_format)
        issueCommentTrigger('^/apply$')
    }

    stages {
        stage('Configure Git') {
            steps {
                withCredentials(bindings: [usernamePassword(credentialsId: '12fe660f-91bf-4848-a946-e49fcc0137f6', usernameVariable: 'GIT_USERNAME', passwordVariable: 'GIT_PASSWORD')]) {
                    sh "git config --global credential.username ${GIT_USERNAME}"
                    sh "git config --global credential.helper '!echo password=${GIT_PASSWORD}; echo'"
                }
            }
        }

        stage('Determine what caused the build') {
            when {
                changeRequest target: 'master'
            }

            steps {
                script {
                    def triggerIssueComment = currentBuild.rawBuild.getCause(org.jenkinsci.plugins.pipeline.github.trigger.IssueCommentCause)

                    if (triggerIssueComment) {
                        // Determine which comment caused the builds
                        if (triggerIssueComment.triggerPattern == '^/apply$') {
                            build_trigger = 'ISSUE_COMMENT_APPLY'
                        } else {
                            build_trigger = 'ISSUE_COMMENT_OTHER'
                        }
                    }
                }
            }
        }

        stage('Determine changes') {
            when {
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                }
            }

            steps {
                script {
                    def previous_commit = ''

                    if (env.GIT_BRANCH == 'master') {
                        try {
                            sh 'gsutil cp gs://jenkins_build_files/successful-commits/ocean-external-address-enforcer /tmp/last-successful-commit'
                            previous_commit = sh (
                                script: "cat /tmp/last-successful-commit",
                                returnStdout: true
                            ).trim()
                        } catch (Exception ignored) {
                            def previous_commit_id = sh (
                                script: "git merge-base ${env.GIT_BRANCH} refs/remotes/origin/master",
                                returnStdout: true
                            ).trim()

                            previous_commit = " ${previous_commit_id}"
                        }
                    } else {
                        def previous_commit_id = sh (
                            script: "git merge-base ${env.GIT_BRANCH} refs/remotes/origin/master",
                            returnStdout: true
                        ).trim()

                        previous_commit = " ${previous_commit_id}"
                    }

                    def changed_dirs = sh (
                        script: "for dir in \$(ls -d */); do chdir=\$(git diff-tree --name-only ${env.GIT_COMMIT} ${previous_commit} \$dir); if ! [ -z \$chdir ] && [ \"\$chdir\" == \"terraform\" ]; then echo \$chdir; fi; done",
                        returnStdout: true
                    ).trim().split('\n')

                    changes = "${changed_dirs}"

                    if (changes.contains('terraform')) {
                        configs_changed = 'YES'
                    }
                }
            }
        }

        stage('Configure Unit Test Environment') {
            when {
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                }
            }
            steps {
                script {
                    try {
                        sh "bash \$(pwd)/tests/test_init.sh"
                        if (env.CHANGE_ID) {
                            pullRequest.comment("Unit Test Environment Configured Successfully")
                        }
                    } catch (Exception e) {
                        if (env.CHANGE_ID) {
                            pullRequest.comment("Unit Test Environment Configuration Error. ${e}")
                        }
                        error 'Unit Test Environment Configuration Error. ${e}'
                    }
                }
            }
        }

        stage('Run Unit Test(s)') {
            when {
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                }
            }
            steps {
                script {
                    try {
                        sh "bash \$(pwd)/tests/test_run.sh"
                        if (env.CHANGE_ID) {
                            pullRequest.comment("Unit Test(s) Completed Successfully")
                        }
                    } catch (Exception e) {
                        if (env.CHANGE_ID) {
                            pullRequest.comment("Unit Test(s) Experienced Issues: ${e}")
                        }
                        error "Unit Test(s) Experienced Issues: ${e}"
                    }
                }
            }
        }

        stage('Packer Build GCE Image(s)') {
            when {
                not { equals expected: 'ISSUE_COMMENT_APPLY', actual: build_trigger }
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                }
            }
            steps {
                script {                 
                    sh "packer build packer.json"                             
                }
            }
        }

        stage('Deploy Test: Terraform Plan') {
            when {
                allOf {
                    equals expected: 'YES', actual: configs_changed
                    changeRequest target: 'master'
                }
            }
            steps {
                script {
                    def deployment = "test"
                    terraformInit("${deployment}")
                    terraformValidate("${deployment}")
                    terraformPlan("${deployment}", "${unique_name}")
                }
            }
        }

        stage('Deploy Test: Terraform Apply') {
            when {
                allOf {
                    equals expected: 'ISSUE_COMMENT_APPLY', actual: build_trigger
                    changeRequest target: 'master'                    
                }
            }
            steps {
                script {
                    def deployment = "test"
                    terraformApply("${deployment}", "${unique_name}")
                }
            }
        }

        stage('Deploy Test: Rolling Replace (gcloud)') {
            when {
                not { equals expected: 'ISSUE_COMMENT_APPLY', actual: build_trigger }
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                    branch 'master'
                }
            }
            steps {
                script {
                    sh "gcloud --project=hsbc-6320774-enforcer-test compute instance-groups managed rolling-action replace gce-igm-europe-west1-t-ip-enforcer --max-surge=3 --max-unavailable=0 --region=europe-west1"
                    sh "gcloud beta --project=hsbc-6320774-enforcer-test compute instance-groups managed wait-until gce-igm-europe-west1-t-ip-enforcer --stable --region=europe-west1"   
                }
            }
        }

        stage('Copy GCE Image to Dev') {
            when {
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                }
            }
            steps {
                script {
                    try {
                        def latest_image = sh (
                            script: "gcloud --project=hsbc-6320774-enforcer-test compute images list \
                            --format='value(NAME)' --filter=family:ocean-ip-enforcer \
                            --sort-by=createTime --limit=1",
                            returnStdout: true
                        ).trim()
                                       
                        def now = new Date()
                        sh (
                            script: "gcloud --project=hsbc-6320774-enforcer-dev compute images create ocean-ip-enforcer-${now.format('yyyyMMddHHmmss')} \
                            --family ocean-ip-enforcer \
                            --source-image=${latest_image} \
                            --source-image-project=hsbc-6320774-enforcer-test --quiet",
                            returnStatus: true
                        )
                    } catch (Exception e) {
                        sh "echo ${e}"
                    } 
                }
            }
        }

        stage('Deploy Dev: Terraform Plan') {
            when {
                allOf {
                    equals expected: 'YES', actual: configs_changed
                    changeRequest target: 'master'
                }
            }
            steps {
                script {
                    def deployment = "dev"
                    terraformInit("${deployment}")
                    terraformValidate("${deployment}")
                    terraformPlan("${deployment}", "${unique_name}")
                }
            }
        }

        stage('Deploy Dev: Terraform Apply') {
            when {
                allOf {
                    equals expected: 'ISSUE_COMMENT_APPLY', actual: build_trigger
                    changeRequest target: 'master'                    
                }
            }
            steps {
                script {
                    def deployment = "dev"
                    terraformApply("${deployment}", "${unique_name}")
                }
            }
        }

        stage('Deploy Dev: Rolling Replace') {
            when {
                not { equals expected: 'ISSUE_COMMENT_APPLY', actual: build_trigger }
                anyOf {
                    triggeredBy "TimerTrigger"
                    changeRequest target: 'master'
                    branch 'master'
                }
            }
            steps {
                script {
                    def deployment = "dev"
                    sh "gcloud --project=hsbc-6320774-enforcer-${deployment} compute instance-groups managed rolling-action replace gce-igm-europe-west1-d-ip-enforcer --max-surge=3 --max-unavailable=0 --region=europe-west1"
                    sh "gcloud beta --project=hsbc-6320774-enforcer-${deployment} compute instance-groups managed wait-until gce-igm-europe-west1-d-ip-enforcer --stable --region=europe-west1"   
                }
            }
        }

        stage('Copy GCE Image to Prod') {
            when { changeRequest target: 'prod' }
            steps {
                script {
                    try {
                        def latest_image = sh (
                            script: "gcloud --project=hsbc-6320774-enforcer-dev compute images list \
                            --format='value(NAME)' --filter=family:ocean-ip-enforcer \
                            --sort-by=createTime --limit=1",
                            returnStdout: true
                        ).trim()
                    
                        def now = new Date()
                        sh (
                            script: "gcloud --project=hsbc-6320774-enforcer-prod compute images create ocean-ip-enforcer-${now.format('yyyyMMddHHmmss')} \
                            --family ocean-ip-enforcer \
                            --source-image=${latest_image} \
                            --source-image-project=hsbc-6320774-enforcer-test --quiet",
                            returnStatus: true
                        )
                    } catch (Exception e) {
                        sh "echo ${e}"
                    }
                }
            }
        }

        stage('Deploy Prod: Terraform Plan') {
            when {
                allOf {
                    equals expected: 'YES', actual: configs_changed
                    changeRequest target: 'master'
                }
            }
            steps {
                script {
                    def deployment = "prod"
                    terraformInit("${deployment}")
                    terraformValidate("${deployment}")
                    terraformPlan("${deployment}", "${unique_name}")
                }
            }
        }

        stage('Deploy Prod: Terraform Apply') {
            when {
                allOf {
                    equals expected: 'ISSUE_COMMENT_APPLY', actual: build_trigger
                    changeRequest target: 'master'                    
                }
            }
            steps {
                script {
                    def deployment = "prod"
                    terraformApply("${deployment}", "${unique_name}")
                }
            }
        }

        stage('Deploy Prod: Rolling Replace') {
            when { changeRequest target: 'prod' }
            steps {
                script {
                    def deployment = "prod"
                    sh "gcloud --project=hsbc-6320774-enforcer-${deployment} compute instance-groups managed rolling-action replace gce-igm-europe-west1-d-ip-enforcer --max-surge=3 --max-unavailable=0 --region=europe-west1"
                    sh "gcloud beta --project=hsbc-6320774-enforcer-${deployment} compute instance-groups managed wait-until gce-igm-europe-west1-d-ip-enforcer --stable --region=europe-west1"   
                }
            }
        }
    }

    post {
        success {
            script {
                // Store last successful commit in GCS
                if (env.GIT_BRANCH == 'master') {
                    sh "echo ${env.GIT_COMMIT} > /tmp/last-successful-commit"
                    sh 'gsutil cp /tmp/last-successful-commit gs://jenkins_build_files/successful-commits/ocean-external-address-enforcer'
                    sh 'rm -f /tmp/last-successful-commit'
                }

                cleanWs()
            }
        }
        cleanup {
            script {
                try {
                    sh 'git config --global --unset credential.helper'
                } catch(Exception e) {}

                cleanWs()
            }
        }
    }
}
