# syntax=docker/dockerfile:1.6
FROM platform-one-ironbank-docker-remote.bits.devops.kratosdefense.com/ironbank/redhat/ubi/ubi9:9.5

# Install required tools
RUN dnf install -y --allowerasing \
      ca-certificates curl bash findutils procps iproute \
      openssh-clients gnupg2 git jq python312 \
  && dnf clean all

# Set working directory for onboarder logic
WORKDIR /docker-workspace
COPY docker-workspace/ /docker-workspace/

# Ensure scripts & tools are executable
RUN find /docker-workspace -type f -name "*.sh" -exec chmod +x {} \; && \
    chmod -R +x /docker-workspace/tools || true

# Environment defaults (constant across runs)
ENV ANSIBLE_CONFIG=/docker-workspace/ansible/ansible.cfg \
    ANSIBLE_ROLES_PATH=/docker-workspace/ansible/roles:/usr/share/ansible/roles \
    ANSIBLE_COLLECTIONS_PATHS=/docker-workspace/ansible/collections \
    TF_PLUGIN_CACHE_DIR=/docker-workspace/terraform/plugins \
    TF_CLI_CONFIG_FILE=/docker-workspace/terraform/terraformrc \
    PATH="/docker-workspace/tools:${PATH}"

CMD ["/docker-workspace/onboarder.sh", "doctor"]