FROM node:20.18.0 as f9
ADD contracts/forkid9.original /app
WORKDIR /app
RUN npm i && npx hardhat compile

FROM node:20.18.0 as f11
ADD contracts/forkid11.original /app
WORKDIR /app
RUN npm i && npx hardhat compile

# TAG: v8.0.0-fork.12
FROM node:20.18.0 as f12
ADD contracts/forkid12.original /app
WORKDIR /app
RUN npm i && npx hardhat compile

FROM node:20.18.0 as f13
ADD contracts/forkid13.original /app
WORKDIR /app
RUN npm i && npx hardhat compile

# Use an official Python runtime as a parent image
FROM python:3.12-slim as final

WORKDIR /app
RUN apt update && apt install -y curl build-essential && \
    rm -fr /var/lib/apt/lists/* /var/cache/apt/*

RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
RUN bash -c "source ~/.bashrc && nvm install v20.18.0"

COPY requirements.txt /app
RUN pip install --no-cache-dir -r requirements.txt

ADD templates /app/templates
COPY deployer_v3.py /app/app.py

RUN ln -s /root/.nvm/versions/node/v20.18.0/bin/npx /usr/local/bin/
RUN ln -s /root/.nvm/versions/node/v20.18.0/bin/node /usr/local/bin/ 

# Delayed so we paralelize as much as possible
COPY --from=f9 /app /app/contracts/forkid9
COPY --from=f11 /app /app/contracts/forkid11
COPY --from=f12 /app /app/contracts/forkid12
COPY --from=f13 /app /app/contracts/forkid13

CMD ["python", "-u", "app.py"]
