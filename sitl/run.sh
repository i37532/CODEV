#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_DIR="$REPO_DIR/.px4-python"
LOCAL_JDK="$REPO_DIR/.sitl-tools/jdk"
LOCAL_ANT="$REPO_DIR/.sitl-tools/root/usr/share/ant"
BACKEND="jmavsim"
MODEL="iris"

usage()
{
	cat <<'EOF'
用法：./sitl/run.sh [--headless] [--backend jmavsim|gazebo] [--model 机型]

示例：
  ./sitl/run.sh
  ./sitl/run.sh --headless
  ./sitl/run.sh --backend gazebo --model iris
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--headless)
			export HEADLESS=1
			shift
			;;
		--backend)
			[[ $# -ge 2 ]] || { usage; exit 2; }
			BACKEND="$2"
			shift 2
			;;
		--model)
			[[ $# -ge 2 ]] || { usage; exit 2; }
			MODEL="$2"
			shift 2
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			echo "错误：未知参数 $1"
			usage
			exit 2
			;;
	esac
done

if [[ ! -x "$REPO_DIR/build/px4_sitl_default/bin/px4" || ! -d "$PYTHON_DIR" ]]; then
	echo "SITL 尚未准备好，正在先执行安装与编译。"
	"$SCRIPT_DIR/setup.sh"
fi

export PYTHONPATH="$PYTHON_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PYTHON_DIR/bin:$PATH"

case "$BACKEND" in
	jmavsim)
		if [[ ! -x "$LOCAL_JDK/bin/java" || ! -x "$LOCAL_ANT/bin/ant" ]]; then
			echo "缺少项目内 Java/Ant，请先运行：$SCRIPT_DIR/setup.sh"
			exit 1
		fi
		export JAVA_HOME="$LOCAL_JDK"
		export ANT_HOME="$LOCAL_ANT"
		export PATH="$JAVA_HOME/bin:$ANT_HOME/bin:$PATH"
		TARGET="jmavsim"
		if [[ "$MODEL" != "iris" ]]; then
			TARGET="jmavsim_$MODEL"
		fi
		;;
	gazebo)
		if ! command -v gazebo >/dev/null 2>&1; then
			echo "错误：尚未安装 Gazebo Classic。请参阅 SITL_CN.md 的 Gazebo 章节。"
			exit 1
		fi
		if [[ "$MODEL" == "iris" && -z "${PX4_SITL_WORLD:-}" ]]; then
			export PX4_SITL_WORLD="$REPO_DIR/sitl/worlds/empty_grey.world"
		fi
		TARGET="gazebo_$MODEL"
		;;
	*)
		echo "错误：仅支持 jmavsim 或 gazebo 后端。"
		exit 2
		;;
esac

echo "启动 PX4 SITL：后端=$BACKEND，机型=$MODEL，目标=$TARGET"
echo "停止仿真请在 PX4 控制台输入 shutdown，或按 Ctrl+C。"
exec make -C "$REPO_DIR" px4_sitl_default "$TARGET"
