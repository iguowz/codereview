#!/bin/bash

# Git增量代码智能审查与测试用例生成系统 - Docker部署脚本

set -e

echo "=============================================="
echo "Git增量代码智能审查与测试用例生成系统"
echo "Docker部署脚本"
echo "=============================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Docker是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker未安装，请先安装Docker"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose未安装，请先安装Docker Compose"
        exit 1
    fi
    
    print_info "Docker环境检查通过"
}

# 检查环境变量文件
check_env_file() {
    if [ ! -f ".env" ]; then
        print_warn ".env文件不存在，正在创建..."
        if [ -f "env.docker.example" ]; then
            cp env.docker.example .env
            print_info "已创建.env文件，请编辑其中的配置"
            print_warn "请设置DEEPSEEK_API_KEY等必要的环境变量"
            return 1
        else
            print_error "env.docker.example模板文件不存在"
            exit 1
        fi
    fi
    
    # 检查必要的环境变量
    if ! grep -q "DEEPSEEK_API_KEY=your_deepseek_api_key_here" .env && ! grep -q "DEEPSEEK_API_KEY=.*[^[:space:]]" .env; then
        print_warn "请设置DEEPSEEK_API_KEY环境变量"
        return 1
    fi
    
    print_info "环境变量文件检查通过"
    return 0
}

# 创建必要的目录
create_directories() {
    print_info "创建必要的目录..."
    
    mkdir -p config data logs cache
    
    # 设置目录权限
    chmod 755 config data logs cache
    
    print_info "目录创建完成"
}

# 检查配置文件
check_config_files() {
    print_info "检查配置文件..."
    
    if [ ! -f "config/systems.yaml" ]; then
        print_warn "config/systems.yaml不存在，请创建并配置Git系统信息"
        print_info "可以参考config/systems.yaml.example文件"
        return 1
    fi
    
    print_info "配置文件检查通过"
    return 0
}

# 构建和启动服务
start_services() {
    print_info "构建Docker镜像..."
    docker-compose build
    
    print_info "启动服务..."
    docker-compose up -d
    
    print_info "等待服务启动..."
    sleep 10
    
    # 检查服务状态
    if docker-compose ps | grep -q "Up"; then
        print_info "服务启动成功！"
        print_info "访问地址: http://localhost:5001"
        print_info "查看日志: docker-compose logs -f"
        print_info "停止服务: docker-compose down"
    else
        print_error "服务启动失败，请检查日志"
        docker-compose logs
        exit 1
    fi
}

# 显示服务状态
show_status() {
    echo ""
    echo "=============================================="
    echo "服务状态"
    echo "=============================================="
    docker-compose ps
    
    echo ""
    echo "=============================================="
    echo "常用命令"
    echo "=============================================="
    echo "查看日志:     docker-compose logs -f"
    echo "停止服务:     docker-compose down"
    echo "重启服务:     docker-compose restart"
    echo "更新服务:     docker-compose pull && docker-compose up -d"
    echo "进入容器:     docker-compose exec codereview bash"
    echo ""
}

# 主函数
main() {
    print_info "开始Docker部署..."
    
    # 检查Docker环境
    check_docker
    
    # 检查环境变量文件
    if ! check_env_file; then
        print_error "请先配置.env文件"
        exit 1
    fi
    
    # 创建目录
    create_directories
    
    # 检查配置文件
    if ! check_config_files; then
        print_warn "配置文件不完整，但可以继续启动服务"
        print_warn "请稍后配置config/systems.yaml文件"
    fi
    
    # 启动服务
    start_services
    
    # 显示状态
    show_status
    
    print_info "部署完成！"
}

# 脚本参数处理
case "${1:-}" in
    "stop")
        print_info "停止服务..."
        docker-compose down
        print_info "服务已停止"
        ;;
    "restart")
        print_info "重启服务..."
        docker-compose restart
        print_info "服务已重启"
        ;;
    "logs")
        docker-compose logs -f
        ;;
    "status")
        docker-compose ps
        ;;
    *)
        main
        ;;
esac
