import { useState, useEffect } from 'react';
import { Button, Space, Typography, Card, Row, Col, Alert, Badge, Tooltip } from 'antd';
import { AppstoreOutlined, LockOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;
import { API_BASE } from '../config';

function AppSelection({ selectedApps, onComplete, onBack }) {
  const [apps, setApps] = useState([]);
  const [selected, setSelected] = useState(selectedApps || []);
  const [loading, setLoading] = useState(true);
  const [resourceSpec, setResourceSpec] = useState('1'); // '1'=4c8g, '2'=8c16g

  useEffect(() => {
    fetchApps();
  }, []);

  const fetchApps = async () => {
    try {
      const response = await axios.get(`${API_BASE}/apps/list`);
      const data = response.data;

      // Merge all apps (base + extended)
      const allApps = data.apps || [];
      setApps(allApps);
      setResourceSpec(data.resource_spec || '1');
    } catch (error) {
      console.error('Failed to fetch apps:', error);
      // Fallback: all apps shown, some disabled
      setApps([
        { id: 'grafana', name: 'Grafana', description: 'Metrics visualization', icon: '📊' },
        { id: 'minio', name: 'MinIO', description: 'Object storage', icon: '🗄️' },
        { id: 'mcpclient', name: 'MCP Client', description: 'AI integrations', icon: '🤖' },
        { id: 'elk', name: 'ELK Stack', description: 'Log analytics', icon: '🔍', requires_high_resource: true },
        { id: 'gitea', name: 'Gitea', description: 'Git service', icon: '🔀', requires_high_resource: true }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const isAppAvailable = (app) => {
    // 8c16g-only apps unavailable in 4c8g mode
    return !(resourceSpec === '1' && app.requires_high_resource);
  };

  const handleToggle = (app) => {
    if (!isAppAvailable(app)) return; // Disabled apps don't toggle

    setSelected(prev =>
      prev.includes(app.id)
        ? prev.filter(id => id !== app.id)
        : [...prev, app.id]
    );
  };

  return (
    <div>
      <Title level={3}>Select Optional Apps</Title>
      <Text type="secondary">
        Choose additional services alongside supOS platform
      </Text>

      <Alert
        message="Core services install automatically"
        description="PostgreSQL, Keycloak, EMQX, Kong, Backend, Frontend, Node-RED, Portainer, Chat2DB, TDengine"
        type="info"
        showIcon
        style={{ margin: '20px 0' }}
      />

      <Row gutter={[16, 16]} style={{ marginTop: 30 }}>
        {apps.map(app => {
          const available = isAppAvailable(app);
          const isSelected = selected.includes(app.id);

          const card = (
            <Card
              hoverable={available}
              onClick={() => available && handleToggle(app)}
              style={{
                border: isSelected ? '2px solid #1890ff' : '1px solid #d9d9d9',
                cursor: available ? 'pointer' : 'not-allowed',
                opacity: available ? 1 : 0.5,
                backgroundColor: available ? '#fff' : '#f5f5f5'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ fontSize: 32, filter: available ? 'none' : 'grayscale(1)' }}>
                  {app.icon}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Text strong style={{ color: available ? undefined : '#999' }}>
                      {app.name}
                    </Text>
                    {!available && <LockOutlined style={{ color: '#999' }} />}
                    {app.requires_high_resource && (
                      <Badge count="8c16g only" style={{ backgroundColor: '#faad14' }} />
                    )}
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {app.description}
                  </Text>
                </div>
              </div>
            </Card>
          );

          return (
            <Col xs={24} sm={12} key={app.id}>
              {available ? card : (
                <Tooltip title="Requires 8c16g resource spec. Unavailable in 4c8g mode.">
                  {card}
                </Tooltip>
              )}
            </Col>
          );
        })}
      </Row>

      <Space style={{ marginTop: 30 }}>
        <Button onClick={onBack}>Back</Button>
        <Button
          type="primary"
          onClick={() => onComplete(selected)}
          icon={<AppstoreOutlined />}
        >
          Continue with {selected.length} app{selected.length !== 1 ? 's' : ''}
        </Button>
      </Space>
    </div>
  );
}

export default AppSelection;
