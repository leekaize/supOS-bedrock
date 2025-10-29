import { useState, useEffect } from 'react';
import { Table, Button, Space, Tag, message, Modal, Typography, Card } from 'antd';
import {
    PlayCircleOutlined,
    PauseCircleOutlined,
    ReloadOutlined,
    SaveOutlined,
    DashboardOutlined
} from '@ant-design/icons';
import { API_BASE } from '../config';

const { Title, Text } = Typography;

function ContainerManager() {
    const [containers, setContainers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [actionLoading, setActionLoading] = useState({});

    const fetchContainers = async () => {
        try {
            const res = await fetch(`${API_BASE}/supos/status`, {
                credentials: 'include'
            });
            const data = await res.json();
            setContainers(data.containers || []);
        } catch (err) {
            message.error('Failed to fetch containers');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchContainers();
        const interval = setInterval(fetchContainers, 15000);
        return () => clearInterval(interval);
    }, []);

    const handleAction = async (containerId, action) => {
        console.log(`Action: ${action} on ${containerId}`); // DEBUG
        setActionLoading({ [containerId]: action });

        try {
            const res = await fetch(`${API_BASE}/supos/container/${containerId}/${action}`, {
                method: 'POST',
                credentials: 'include'
            });

            console.log('Response:', res.status, await res.text()); // DEBUG

            if (res.ok) {
                message.success(`Container ${action}ed`);
                fetchContainers();
            } else {
                message.error('Action failed');
            }
        } catch (err) {
            console.error('Action error:', err); // DEBUG
            message.error('Network error');
        } finally {
            setActionLoading({});
        }
    };

    const handleBackup = () => {
        Modal.confirm({
            title: 'Create Backup',
            content: 'Backup all volumes and configuration?',
            onOk: async () => {
                try {
                    const res = await fetch(`${API_BASE}/supos/backup`, {
                        method: 'POST',
                        credentials: 'include'
                    });
                    const data = await res.json();
                    if (data.success) {
                        message.success(`Backup created: ${data.backup_path}`);
                    }
                } catch {
                    message.error('Backup failed');
                }
            }
        });
    };

    const openSuposDashboard = async () => {
        try {
            const res = await fetch(`${API_BASE}/setup/status`);
            const data = await res.json();
            const { domain, port } = data.config.network;
            window.open(`http://${domain}:${port}/home`, '_blank');
        } catch {
            message.error('Failed to get dashboard URL');
        }
    };

    const columns = [
        {
            title: 'Container',
            dataIndex: 'name',
            key: 'name',
            render: (name) => <Text strong>{name}</Text>
        },
        {
            title: 'Status',
            dataIndex: 'status',
            key: 'status',
            render: (status) => (
                <Tag color={status === 'running' ? 'success' : 'default'}>
                    {status.toUpperCase()}
                </Tag>
            )
        },
        {
            title: 'Actions',
            key: 'actions',
            render: (_, record) => (
                <Space>
                    {record.status !== 'running' && (
                        <Button
                            size="small"
                            icon={<PlayCircleOutlined />}
                            loading={actionLoading[record.id] === 'start'}
                            onClick={() => handleAction(record.id, 'start')}
                        >
                            Start
                        </Button>
                    )}
                    {record.status === 'running' && (
                        <Button
                            size="small"
                            danger
                            icon={<PauseCircleOutlined />}
                            loading={actionLoading[record.id] === 'stop'}
                            onClick={() => handleAction(record.id, 'stop')}
                        >
                            Stop
                        </Button>
                    )}
                    <Button
                        size="small"
                        icon={<ReloadOutlined />}
                        loading={actionLoading[record.id] === 'restart'}
                        onClick={() => handleAction(record.id, 'restart')}
                    >
                        Restart
                    </Button>
                </Space>
            )
        }
    ];

    const runningCount = containers.filter(c => c.status === 'running').length;

    return (
        <div>
            <Title level={3}>Container Management</Title>

            <Space style={{ margin: '20px 0' }}>
                <Button
                    type="primary"
                    icon={<ReloadOutlined />}
                    onClick={fetchContainers}
                    loading={loading}
                >
                    Refresh
                </Button>
                <Button
                    icon={<DashboardOutlined />}
                    onClick={openSuposDashboard}
                >
                    Open supOS Dashboard
                </Button>
                <Button
                    icon={<SaveOutlined />}
                    onClick={handleBackup}
                >
                    Create Backup
                </Button>
            </Space>

            <Text type="secondary">
                {"\n"}
                {runningCount} of {containers.length} containers running
            </Text>

            <Card>
                <Table
                    columns={columns}
                    dataSource={containers}
                    rowKey="id"
                    loading={loading}
                    pagination={false}
                />
            </Card>
        </div>
    );
}

export default ContainerManager;
