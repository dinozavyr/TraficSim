FROM opensuse/tumbleweed

RUN zypper addrepo https://download.opensuse.org/repositories/home:/behrisch/openSUSE_Tumbleweed/home:behrisch.repo
RUN zypper --no-gpg-checks --gpg-auto-import-keys refresh
RUN zypper install -y sumo

RUN zypper in -y patterns-devel-python-devel_python3 patterns-devel-base-devel_basis patterns-devel-C-C++-devel_C_C++ gcc-c++ python310-devel python310-pip python310-wheel python310-pip-wheel

WORKDIR /app
COPY ./config/ ./config/
RUN mkdir data
COPY ./traficsim/ ./traficsim/
COPY requirements.txt requirements.txt

RUN pip install --upgrade pip && pip install -r requirements.txt

ENV PYTHONPATH '/app'

CMD ["sh", "-c", "python3", "/app/main.py", "--uuid=$UUID", "--algo=$ALGO", "--vtype=$VTYPE", "--interval=$INTERVAL"]

