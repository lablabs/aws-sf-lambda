FROM amazonlinux:1
ENV NAME=''
RUN yum install -y python36-pip zip && yum clean all
COPY src /build
RUN pip-3.6 install -r /build/requirements.txt -t /build/vendored/
WORKDIR /build
CMD sh build_package.sh ${NAME}
