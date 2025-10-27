import { useState, useEffect } from 'react';
import { Button, Alert, Spin, List, Typography, Form, Input, Select, Space, Card, Radio } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, WarningOutlined, SettingOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;
const { Option } = Select;

import { API_BASE } from '../config';

function SystemValidation({ onComplete }) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [validationResult, setValidationResult] = useState(null);
  const [configSaved, setConfigSaved] = useState(false);
  const [loopbackWarning, setLoopbackWarning] = useState(false);
  const [volumeCheck, setVolumeCheck] = useState(null);
  const [detectedIPs, setDetectedIPs] = useState([]);
  const [ipMode, setIpMode] = useState('detected'); // 'detected' or 'custom'

  useEffect(() => {
    runValidation();
    checkVolume();
    loadDetectedIPs();
  }, []);

  const loadDetectedIPs = async () => {
    try {
      const response = await axios.get(`${API_BASE}/config/detected-ips`);
      const { detected_ips, default_port } = response.data;

      setDetectedIPs(detected_ips);

      // Pre-select first non-loopback IP if available
      const defaultIP = detected_ips.find(ip => ip !== '127.0.0.1') || detected_ips[0] || '127.0.0.1';

      form.setFieldsValue({
        ip_detected: defaultIP,
        entrance_port: default_port,
        resource_spec: '1'
      });

      // Check if default is loopback
      setLoopbackWarning(defaultIP === '127.0.0.1' || defaultIP === 'localhost');
    } catch (error) {
      console.error('Failed to load detected IPs:', error);
      setDetectedIPs(['127.0.0.1']);
      form.setFieldsValue({
        ip_detected: '127.0.0.1',
        entrance_port: '8088',
        resource_spec: '1'
      });
    }
  };

  const checkVolume = async () => {
    try {
      const response = await axios.get(`${API_BASE}/config/check-volume`);
      setVolumeCheck(response.data);
    } catch (error) {
      setVolumeCheck({
        mounted: false,
        error: 'Failed to check volume: ' + error.message
      });
    }
  };

  const runValidation = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`${API_BASE}/setup/validate`);
      setValidationResult(response.data);
    } catch (error) {
      setValidationResult({
        valid: false,
        issues: [`API Error: ${error.message}`],
        warnings: []
      });
    } finally {
      setLoading(false);
    }
  };

  const handleIpChange = (value) => {
    const isLoopback = value === '127.0.0.1' || value === 'localhost';
    setLoopbackWarning(isLoopback);
  };

  const handleSubmit = async (values) => {
    setLoading(true);

    try {
      // Get IP based on mode
      const ip_address = ipMode === 'detected'
        ? values.ip_detected
        : values.ip_custom?.trim();

      const entrance_port = values.entrance_port?.trim() || '8088';

      if (!ip_address) {
        throw new Error('IP address is required');
      }

      // Loopback confirmation
      const isLoopback = ip_address === '127.0.0.1' || ip_address === 'localhost';
      if (isLoopback) {
        const confirmed = window.confirm(
          '⚠️ WARNING: You are using a loopback address. OAuth function will NOT work.\n\n' +
          'Proceed without login?'
        );
        if (!confirmed) {
          setLoading(false);
          return;
        }
      }

      // Save config (creates .env for first time)
      const response = await axios.post(`${API_BASE}/config/update`, {
        ip_address: ip_address,
        entrance_port: entrance_port,
        resource_spec: values.resource_spec
      });

      if (response.data.success) {
        setConfigSaved(true);
        setTimeout(() => onComplete(true), 1000);
      } else {
        throw new Error(response.data.error || 'Failed to save configuration');
      }
    } catch (error) {
      alert(`Configuration save failed: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  if (loading && !validationResult) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        <Spin size="large" />
        <Title level={4} style={{ marginTop: 20 }}>Validating system...</Title>
      </div>
    );
  }

  return (
    <div>
      <Title level={3}>System Configuration</Title>
      <Text type="secondary">Validate requirements and configure platform settings</Text>

      {/* Volume Check Result */}
      {volumeCheck && (
        <>
          {volumeCheck.mounted && volumeCheck.writable ? (
            <Alert
              message="Data Volume Ready"
              description={
                <div>
                  <div><strong>Path:</strong> {volumeCheck.path}</div>
                  <div><strong>Available:</strong> {volumeCheck.free_gb}GB / {volumeCheck.total_gb}GB</div>
                  {!volumeCheck.sufficient && (
                    <div style={{ color: '#faad14', marginTop: 8 }}>
                      ⚠️ Warning: Less than 20GB available. Consider freeing up space.
                    </div>
                  )}
                </div>
              }
              type="success"
              icon={<CheckCircleOutlined />}
              showIcon
              style={{ margin: '20px 0' }}
            />
          ) : (
            <Alert
              message="Volume Mount Issue"
              description={
                <div>
                  <div style={{ marginBottom: 8 }}>
                    Volume is not mounted or not writable. Re-run docker command:
                  </div>
                  <div style={{ fontFamily: 'monospace', background: '#f5f5f5', padding: 8, fontSize: 12 }}>
                    docker run -d \<br />
                    &nbsp;&nbsp;--name supos-bedrock \<br />
                    &nbsp;&nbsp;--restart always \<br />
                    &nbsp;&nbsp;-p 8080:8080 \<br />
                    &nbsp;&nbsp;-e HOST_IP=$(hostname -I | awk '&#123;print $1&#125;') \<br />
                    &nbsp;&nbsp;-v /var/run/docker.sock:/var/run/docker.sock \<br />
                    &nbsp;&nbsp;<strong>-v /volumes/supos/data:/volumes/supos/data</strong> \<br />
                    &nbsp;&nbsp;leekaize/supos-bedrock:latest
                  </div>
                </div>
              }
              type="error"
              showIcon
              style={{ margin: '20px 0' }}
            />
          )}
        </>
      )}

      {/* System Validation Results */}
      {validationResult && (
        <>
          {validationResult.valid && (
            <Alert
              message="System checks passed"
              description="Your system meets all requirements"
              type="success"
              icon={<CheckCircleOutlined />}
              showIcon
              style={{ margin: '20px 0' }}
            />
          )}

          {validationResult.issues && validationResult.issues.length > 0 && (
            <Alert
              message="Requirements not met"
              description={
                <List
                  size="small"
                  dataSource={validationResult.issues}
                  renderItem={(item) => (
                    <List.Item>
                      <CloseCircleOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />
                      {item}
                    </List.Item>
                  )}
                />
              }
              type="error"
              showIcon
              style={{ margin: '20px 0' }}
            />
          )}

          {validationResult.warnings && validationResult.warnings.length > 0 && (
            <Alert
              message="Warnings"
              description={
                <List
                  size="small"
                  dataSource={validationResult.warnings}
                  renderItem={(item) => (
                    <List.Item>
                      <WarningOutlined style={{ color: '#faad14', marginRight: 8 }} />
                      {item}
                    </List.Item>
                  )}
                />
              }
              type="warning"
              showIcon
              style={{ margin: '20px 0' }}
            />
          )}
        </>
      )}

      {/* Configuration Form */}
      <Card
        title={
          <Space>
            <SettingOutlined />
            <span>Network Configuration</span>
          </Space>
        }
        style={{ marginTop: 30 }}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
        >
          <Form.Item
            label="IP Address / Domain"
            extra={
              ipMode === 'detected'
                ? "Select from detected network interfaces"
                : "Enter your server's IP address or custom domain"
            }
          >
            <Radio.Group
              value={ipMode}
              onChange={(e) => {
                setIpMode(e.target.value);
                setLoopbackWarning(false);
              }}
              style={{ marginBottom: 12 }}
            >
              <Radio value="detected">Detected IPs</Radio>
              <Radio value="custom">Custom IP/Domain</Radio>
            </Radio.Group>

            {ipMode === 'detected' ? (
              <Form.Item
                name="ip_detected"
                noStyle
                rules={[{ required: ipMode === 'detected', message: 'Please select an IP' }]}
              >
                <Select
                  size="large"
                  placeholder="Select IP address"
                  onChange={handleIpChange}
                >
                  {detectedIPs.map(ip => (
                    <Option key={ip} value={ip}>
                      {ip}{ip === '127.0.0.1' ? ' (localhost - dev only)' : ''}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            ) : (
              <Form.Item
                name="ip_custom"
                noStyle
                rules={[
                  { required: ipMode === 'custom', message: 'Please enter an IP address' }
                ]}
              >
                <Input
                  size="large"
                  placeholder="192.168.1.100 or example.com"
                  onChange={(e) => handleIpChange(e.target.value)}
                />
              </Form.Item>
            )}
          </Form.Item>

          {loopbackWarning && (
            <Alert
              message="⚠️ Loopback Address Detected"
              description="OAuth authentication will be disabled. Use 127.0.0.1 only for local development."
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}

          <Form.Item
            label="Entrance Port"
            name="entrance_port"
            rules={[
              { required: true, message: 'Port is required' },
              { pattern: /^\d+$/, message: 'Must be a number' }
            ]}
            extra="Default: 8088. Ensure port is not already in use."
          >
            <Input size="large" placeholder="8088" />
          </Form.Item>

          <Form.Item
            label="Resource Specification"
            name="resource_spec"
            rules={[{ required: true, message: 'Resource spec is required' }]}
            extra="Choose based on your server capacity"
          >
            <Select size="large">
              <Option value="1">4 CPU / 8GB RAM (Minimum)</Option>
              <Option value="2">8 CPU / 16GB RAM (Recommended)</Option>
            </Select>
          </Form.Item>

          <Form.Item style={{ marginTop: 30 }}>
            <Space>
              {(!validationResult?.valid || !volumeCheck?.mounted) && (
                <Button onClick={() => { runValidation(); checkVolume(); }}>
                  Retry Validation
                </Button>
              )}
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                disabled={!validationResult?.valid || !volumeCheck?.mounted}
                size="large"
              >
                {configSaved ? 'Configuration Saved!' : 'Save & Continue'}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}

export default SystemValidation;
