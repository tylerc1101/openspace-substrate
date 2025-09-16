# syntax=docker/dockerfile:1.7

# ==================================================================
# Builder Stage
#
# Installs all necessary tools and dependencies.
# ==================================================================
FROM platform-one-ironbank-docker-remote.bits.devops.kratosdefense.com/ironbank/redhat/ubi/ubi9:9.5 AS builder

# Install build-time dependencies and required runtime tools
RUN --mount=type=cache,target=/var/cache/dnf \
    dnf install -y \
      # Runtime tools
      ca-certificates bash findutils procps iproute \
      openssh-clients gnupg2 git python312 \
      # Cleanup
  && dnf clean all

# ==================================================================
# Final Stage
#
# Creates a minimal final image with a non-root user.
# ==================================================================

# Add OCI labels for metadata
LABEL org.opencontainers.image.source="https://github.com/tylerc1101/openspace-substrate"
LABEL org.opencontainers.image.description="Onboarder container for managing infrastructure deployments."
LABEL org.opencontainers.image.licenses="MIT"

# Create a non-root user and group
RUN groupadd --gid 10001 onboarder \
 && useradd --uid 10001 --gid 10001 --shell /bin/bash --create-home onboarder

# Copy installed tools from the builder stage
COPY --from=builder / /

# Set up the workspace directory
WORKDIR /docker-workspace
COPY --chown=onboarder:onboarder docker-workspace/ /docker-workspace/
RUN chmod +x /docker-workspace/onboarder.py

# Environment defaults (constant across runs)
ENV ANSIBLE_CONFIG=/docker-workspace/ansible/ansible.cfg \
    ANSIBLE_ROLES_PATH=/docker-workspace/ansible/roles:/usr/share/ansible/roles \
    ANSIBLE_COLLECTIONS_PATHS=/docker-workspace/ansible/collections \
    TF_PLUGIN_CACHE_DIR=/docker-workspace/terraform/plugins \
    TF_CLI_CONFIG_FILE=/docker-workspace/terraform/terraformrc \
    PATH="/docker-workspace/tools:${PATH}"

# Switch to the non-root user
USER onboarder:onboarder

# Healthcheck to monitor container status
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD [ "/docker-workspace/onboarder.py", "doctor" ]

# Default command to run when the container starts
CMD ["/docker-workspace/onboarder.py", "doctor"]
