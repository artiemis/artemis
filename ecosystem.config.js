module.exports = {
  apps: [
    {
      name: "artemis",
      script: "./env/bin/python",
      args: "-m artemis.bot",
      time: true,
      env: {
        PYTHONUNBUFFERED: "1",
        ENV: "production",
      },
    },
  ],
};
