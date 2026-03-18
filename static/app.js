// 전역 유틸리티
document.addEventListener('DOMContentLoaded', function() {
    // 플래시 메시지 자동 닫기
    document.querySelectorAll('.flash').forEach(el => {
        setTimeout(() => {
            el.style.opacity = '0';
            setTimeout(() => el.remove(), 300);
        }, 4000);
    });

    // 파일 선택 시 파일명 표시
    const fileInput = document.getElementById('importFile');
    if (fileInput) {
        fileInput.addEventListener('change', function() {
            const label = this.nextElementSibling;
            if (this.files.length > 0) {
                label.textContent = this.files[0].name;
            }
        });
    }
});
