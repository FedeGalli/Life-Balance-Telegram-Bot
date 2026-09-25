docker stop $(docker ps -a -q)
docker rm $(docker ps -a -q)
docker rmi -f $(docker images -aq)
docker build . -t life-balance-image
docker run --restart=always -e BOT_DATA_DIRECTORY=/data -v life-balance-data:/data life-balance-image
