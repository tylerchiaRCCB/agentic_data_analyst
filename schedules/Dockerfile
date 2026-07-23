################################################################################
# Agentic Data Analyst — Docker image for AML pipeline jobs
#
# 1. Verify logged in to Azure:
#    az login
#    az acr login --name ccbdsmldev
#
# 2. Build:
#    docker build -t ccbdsmldev.azurecr.io/agentic-data-analyst-image:latest .
#
# 3. Push to ACR:
#    docker push ccbdsmldev.azurecr.io/agentic-data-analyst-image:latest
#
# 4. Test:
#    docker run -it ccbdsmldev.azurecr.io/agentic-data-analyst-image:latest /bin/bash
#    source activate agentic-data-analyst-env
#    python -c "import anthropic; print('OK')"
#    exit
#
# 5. Register AML environment (if not using create_docker_image.py):
#    python create_docker_image.py
################################################################################

FROM anaconda/miniconda

USER root

ARG ENV_NAME=agentic-data-analyst-env

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y git libstdc++6 && rm -rf /var/lib/apt/lists/*

# Copy environment file
COPY environment.yml .

# Accept Anaconda Terms of Service for default channels
RUN conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# Create the Conda environment
RUN conda env create -f environment.yml

# Ensure conda is initialized for bash
RUN conda init bash

# Clean up
RUN conda clean -aqy && \
    rm -rf /opt/miniconda3/pkgs/* && \
    find /opt/miniconda3/ -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Set environment PATH so the conda env is always active (required for AML jobs)
ENV PATH="/opt/miniconda3/envs/${ENV_NAME}/bin:/opt/miniconda3/bin:${PATH}"

CMD ["/bin/bash"]
