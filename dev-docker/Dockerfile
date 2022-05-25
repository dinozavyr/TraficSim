FROM apache/airflow:1.10.14-python3.6

USER root
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
RUN curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg  add -
RUN bash -c "apt-get update \
        && apt-get install --yes \
            gcc build-essential python3-dev google-cloud-sdk kubectl"
      
RUN python -m pip install --upgrade pip
RUN python -m pip install argcomplete \
            google \
            google-api-python-client \
            google-cloud-bigquery \
            google-cloud-bigquery-storage \
            google-cloud-secret-manager \
            google-cloud-storage \
            lxml \
            numpy \
            pandas \
            pyarrow \
            mmh3 \
            requests \
            gcsfs \
            paramiko \
            sshtunnel \
            newspaper3k \
            googlenews \
            urllib3 \
            pandas \
            pandas-gbq

USER airflow