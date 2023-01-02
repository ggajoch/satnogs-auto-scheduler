# SatNOGS auto-scheduler image
#
# Copyright (C) 2022 Libre Space Foundation <https://libre.space/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

FROM python:3.9-slim
LABEL org.opencontainers.image.authors='sa2kng <knegge@gmail.com>'

ARG SATNOGS_CLIENT_UID=999
ARG SATNOGS_CLIENT_NAME=satnogs-client
ARG SATNOGS_CLIENT_VARSTATEDIR=/var/lib/satnogs-client

# Add unprivileged system user
RUN groupadd -r -g ${SATNOGS_CLIENT_UID} ${SATNOGS_CLIENT_NAME} \
	&& useradd -r -u ${SATNOGS_CLIENT_UID} \
		-g ${SATNOGS_CLIENT_NAME} \
		-d ${SATNOGS_CLIENT_VARSTATEDIR} \
		-s /usr/bin/false \
		-G audio,dialout,plugdev \
		${SATNOGS_CLIENT_NAME}

# Create application varstate directory
RUN install -d -o ${SATNOGS_CLIENT_UID} -g ${SATNOGS_CLIENT_UID} ${SATNOGS_CLIENT_VARSTATEDIR}

# Copy source code
COPY . /usr/local/src/satnogs-auto-scheduler/

# Install Python dependencies and application
RUN echo "[global]" > /etc/pip.conf \
	&& echo "extra-index-url=https://www.piwheels.org/simple" >> /etc/pip.conf \
	&& pip install --no-cache-dir --prefer-binary \
		/usr/local/src/satnogs-auto-scheduler

USER ${SATNOGS_CLIENT_NAME}
WORKDIR ${SATNOGS_CLIENT_VARSTATEDIR}
CMD ["bash"]

