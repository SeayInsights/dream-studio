FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root developer user
RUN useradd -m -s /bin/bash developer
USER developer
WORKDIR /home/developer

# Create the .claude directory structure that
# Claude Code would normally create
# (empty — simulating a fresh Claude Code install)
RUN mkdir -p /home/developer/.claude/skills \
    /home/developer/.claude/agents \
    /home/developer/.claude/workflows \
    /home/developer/.claude/hooks

# Copy repo into container at the expected path
COPY --chown=developer:developer . \
    /home/developer/builds/dream-studio-clean

# Set Python path
ENV PYTHONPATH=/home/developer/builds/dream-studio-clean

WORKDIR /home/developer/builds/dream-studio-clean

# Default: run the clean install test
CMD ["/bin/bash", "-c", \
    "python3 -m interfaces.cli.ds integrate install claude_code --execute && \
     echo '=== DOCTOR ===' && \
     python3 -m interfaces.cli.ds doctor && \
     echo '=== VERIFY INSTALLED FILES ===' && \
     find /home/developer/.claude -type f | sort && \
     echo '=== DONE ==='"]
