import { useState, useEffect } from 'react';
import { Table, Button, Space, Tag, message, Modal, Typography, Card, Badge, Tooltip } from 'antd';
import {
    PlayCircleOutlined,
    PauseCircleOutlined,
    ReloadOutlined,
    SaveOutlined,
    DashboardOutlined,
    CloudUploadOutlined
} from '@ant-design/icons';
import { authAPI } from '../utils/authFetch';
import { API_BASE } from '../config';

const { Title, Text } = Typography;

function ContainerManager() {
    const [containers, setContainers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [actionLoading, setActionLoading] = useState({});
    const [updateModal, setUpdateModal] = useState({ visible: false, container: null });

    const fetchContainers = async () => {
        try {
            const data = await authAPI.get('/versions/compare');
            setContainers(data.containers || []);
        } catch (err) {
            console.error('Fetch error:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchContainers();
        const interval = setInterval(fetchContainers, 30000);
        return () => clearInterval(interval);
    }, []);

    const handleAction = async (containerId, action) => {
        setActionLoading({ [containerId]: action });

        try {
            await authAPI.post(`/supos/container/${containerId}/${action}`);
            message.success(`Container ${action}ed`);
            fetchContainers();
        } catch (err) {
            console.error('Action error:', err);
        } finally {
            setActionLoading({});
        }
    };

    const handleUpdate = (containerName, currentVersion, recommendedVersion) => {
        setUpdateModal({
            visible: true,
            container: { containerName, currentVersion, recommendedVersion }
        });
    };

    const executeUpdate = async () => {
        const { containerName, currentVersion, recommendedVersion } = updateModal.container;
        setUpdateModal({ visible: false, container: null });

        // Mark container as updating - keep it in list
        setContainers(prev => prev.map(c =>
            c.name === containerName
                ? { ...c, status: 'updating', _isUpdating: true }
                : c
        ));

        setActionLoading({ [containerName]: 'updating' });

        try {
            const data = await authAPI.post(`/container/${containerName}/update`);

            if (data.success) {
                message.success(data.message);

                // Poll for container to come back
                let attempts = 0;
                const pollInterval = setInterval(async () => {
                    attempts++;

                    try {
                        const freshData = await authAPI.get('/versions/compare');
                        const updatedContainer = freshData.containers.find(c => c.name === containerName);

                        if (updatedContainer && updatedContainer.status === 'running') {
                            clearInterval(pollInterval);
                            setContainers(freshData.containers);
                            setActionLoading({});
                            message.success(`${containerName} is now running ${updatedContainer.current_version}`);
                        } else if (attempts > 30) {
                            // Give up after 60 seconds
                            clearInterval(pollInterval);
                            setActionLoading({});
                            fetchContainers();
                            message.warning('Update completed but container status unclear. Refresh to verify.');
                        }
                    } catch (err) {
                        console.error('Poll error:', err);
                    }
                }, 2000);
            } else {
                message.error(data.error || 'Update failed');
                fetchContainers();
                setActionLoading({});
            }
        } catch (err) {
            console.error('Update error:', err);
            fetchContainers();
            setActionLoading({});
        }
    };

    const handleBackup = () => {
        Modal.confirm({
            title: 'Create Backup',
            content: 'Backup all volumes and configuration?',
            onOk: async () => {
                try {
                    const data = await authAPI.post('/supos/backup');
                    if (data.success) {
                        message.success(`Backup created: ${data.backup_path}`);
                    }
                } catch (err) {
                    console.error('Backup error:', err);
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
            render: (name, record) => (
                <Space direction="vertical" size={0}>
                    <Text strong>{name}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>{record.image}</Text>
                </Space>
            )
        },
        {
            title: 'Status',
            dataIndex: 'status',
            key: 'status',
            render: (status) => (
                <Tag color={status === 'running' ? 'green' : status === 'exited' ? 'red' : 'orange'}>
                    {status.toUpperCase()}
                </Tag>
            )
        },
        {
            title: 'Version',
            key: 'version',
            render: (_, record) => (
                <Space direction="vertical" size={0}>
                    <Space>
                        <Text>Current:</Text>
                        <Tag color="blue">{record.current_version}</Tag>
                    </Space>
                    {record.recommended_version && (
                        <Space>
                            <Text>Latest:</Text>
                            <Tag color={record.update_available ? 'orange' : 'green'}>
                                {record.recommended_version}
                            </Tag>
                        </Space>
                    )}
                </Space>
            )
        },
        {
            title: 'Update Status',
            key: 'update_status',
            render: (_, record) => {
                if (!record.recommended_version) {
                    return <Tag>No manifest data</Tag>;
                }
                if (record.update_available) {
                    return (
                        <Tooltip title="New version available">
                            <Badge status="warning" text="Update Available" />
                        </Tooltip>
                    );
                }
                return (
                    <Tooltip title="Running latest version">
                        <Badge status="success" text="Up to Date" />
                    </Tooltip>
                );
            }
        },
        {
            title: 'Actions',
            key: 'actions',
            render: (_, record) => (
                <Space>
                    {record.status === 'running' ? (
                        <Button
                            size="small"
                            icon={<PauseCircleOutlined />}
                            onClick={() => handleAction(record.id, 'stop')}
                            loading={actionLoading[record.id] === 'stop'}
                        >
                            Stop
                        </Button>
                    ) : (
                        <Button
                            size="small"
                            icon={<PlayCircleOutlined />}
                            onClick={() => handleAction(record.id, 'start')}
                            loading={actionLoading[record.id] === 'start'}
                        >
                            Start
                        </Button>
                    )}
                    <Button
                        size="small"
                        icon={<ReloadOutlined />}
                        onClick={() => handleAction(record.id, 'restart')}
                        loading={actionLoading[record.id] === 'restart'}
                    >
                        Restart
                    </Button>
                    {record.update_available && (
                        <Button
                            size="small"
                            type="primary"
                            icon={<CloudUploadOutlined />}
                            onClick={() => handleUpdate(
                                record.name,
                                record.current_version,
                                record.recommended_version
                            )}
                            loading={actionLoading[record.name] === 'updating'}
                        >
                            Update
                        </Button>
                    )}
                </Space>
            )
        }
    ];

    const updatesAvailable = containers.filter(c => c.update_available).length;

    return (
        <div style={{ padding: 24 }}>
            <Card>
                <Space direction="vertical" style={{ width: '100%' }} size="large">
                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <div>
                            <Title level={3}>Container Management</Title>
                            {updatesAvailable > 0 && (
                                <Badge
                                    count={updatesAvailable}
                                    style={{ backgroundColor: '#faad14' }}
                                >
                                    <Text type="secondary">Updates Available</Text>
                                </Badge>
                            )}
                        </div>
                        <Space>
                            <Button
                                icon={<ReloadOutlined />}
                                onClick={fetchContainers}
                                loading={loading}
                            >
                                Refresh
                            </Button>
                            <Button
                                icon={<SaveOutlined />}
                                onClick={handleBackup}
                            >
                                Backup
                            </Button>
                            <Button
                                type="primary"
                                icon={<DashboardOutlined />}
                                onClick={openSuposDashboard}
                            >
                                Open Dashboard
                            </Button>
                        </Space>
                    </Space>

                    <Table
                        columns={columns}
                        dataSource={containers}
                        rowKey="id"
                        loading={loading}
                        pagination={false}
                    />
                </Space>
            </Card>

            <Modal
                title="Update Container"
                open={updateModal.visible}
                onOk={executeUpdate}
                onCancel={() => setUpdateModal({ visible: false, container: null })}
                okText="Update"
                cancelText="Cancel"
                okButtonProps={{ danger: true }}
            >
                {updateModal.container && (
                    <div>
                        <p>Update <strong>{updateModal.container.containerName}</strong>?</p>
                        <p>Current: <Tag color="blue">{updateModal.container.currentVersion}</Tag></p>
                        <p>New: <Tag color="green">{updateModal.container.recommendedVersion}</Tag></p>
                        <p style={{ marginTop: 16, color: '#ff4d4f' }}>
                            ⚠️ Container will be stopped and recreated. This may take 1-2 minutes.
                        </p>
                    </div>
                )}
            </Modal>
        </div>
    );
}

export default ContainerManager;
