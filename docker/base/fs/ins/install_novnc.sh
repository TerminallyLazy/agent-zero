#!/bin/bash
set -e

echo "====================NOVNC INSTALL START===================="

# Install noVNC for web-based VNC access
cd /opt
git clone https://github.com/novnc/noVNC.git
cd noVNC
git checkout v1.3.0

# Install websockify
cd /opt
git clone https://github.com/novnc/websockify.git
cd websockify
python3 setup.py install

# Create noVNC startup script
cat > /usr/local/bin/start-novnc.sh << 'EOF'
#!/bin/bash
# Start noVNC on port 6080
cd /opt/noVNC
./utils/launch.sh --vnc localhost:5901 --listen 6080 &
EOF

chmod +x /usr/local/bin/start-novnc.sh

echo "====================NOVNC INSTALL END===================="