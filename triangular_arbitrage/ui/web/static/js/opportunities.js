import analyzer from './analysis.js';

class OpportunitiesManager {
    constructor() {
        this.table = document.getElementById('opportunities-body');
        this.countElement = document.getElementById('opportunity-count');
        this.lastUpdateElement = document.getElementById('last-update');
        this.autoRefreshButton = document.getElementById('auto-refresh');
        this.autoRefresh = true;
        this.wsManager = window.wsManager;
        this.setupEventListeners();
        this.initializeWebSocket();
    }

    initializeWebSocket() {
        // Inscreve-se para receber atualizações de oportunidades
        this.wsManager.subscribe('opportunities', (data) => {
            if (this.autoRefresh) {
                this.updateOpportunities(data);
            }
        });

        // Solicita dados iniciais
        this.wsManager.ws.send(JSON.stringify({
            type: 'subscribe',
            topics: ['opportunities']
        }));
    }

    setupEventListeners() {
        if (this.autoRefreshButton) {
            this.autoRefreshButton.addEventListener('click', () => {
                this.autoRefresh = !this.autoRefresh;
                this.autoRefreshButton.classList.toggle('bg-indigo-200', this.autoRefresh);
                this.autoRefreshButton.textContent = this.autoRefresh ? 'Auto Refresh On' : 'Auto Refresh Off';
            });
        }
    }

    async analyzeOpportunity(route) {
        try {
            const response = await fetch(`/api/analyze-route?route=${encodeURIComponent(route)}`);
            if (!response.ok) {
                throw new Error('Erro ao analisar rota');
            }
            const data = await response.json();
            analyzer.showAnalysisModal(data);
        } catch (error) {
            console.error('Erro ao analisar oportunidade:', error);
            analyzer.showError('Não foi possível analisar esta oportunidade');
        }
    }

    updateOpportunities(data) {
        if (!this.table || !this.autoRefresh) return;
        if (!data || !data.data) return;

        const opportunities = data.data;
        const metadata = data.metadata || {};

        // Limpa tabela atual
        this.table.innerHTML = '';
        
        if (!opportunities || opportunities.length === 0) {
            this.showNoDataMessage();
            this.updateCount(0);
            return;
        }

        opportunities.forEach(opp => {
            const row = document.createElement('tr');
            row.className = 'hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors';
            
            const profit = parseFloat(opp.profit);
            const profitClass = profit > 1.0 ? 'text-green-600 dark:text-green-400' : 
                              profit > 0.5 ? 'text-yellow-600 dark:text-yellow-400' : 
                              'text-gray-600 dark:text-gray-400';
            
            const statusClass = opp.status === 'active' ? 
                'bg-green-100 text-green-800 dark:bg-green-700 dark:text-green-100' :
                'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-100';

            row.innerHTML = `
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                    ${this.formatRoute(opp.route)}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm ${profitClass}">
                    ${profit.toFixed(4)}%
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">
                    ${parseFloat(opp.volume || 0).toFixed(8)}
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${statusClass}">
                        ${opp.status}
                    </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">
                    ${this.formatTimestamp(opp.timestamp)}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">
                    ${opp.status === 'active' ? `
                        <button onclick="window.opportunitiesManager.monitorOpportunity('${opp.route}')" 
                                class="text-indigo-600 hover:text-indigo-900 dark:text-indigo-400 dark:hover:text-indigo-300 mr-3">
                            Monitor
                        </button>
                        <button onclick="window.opportunitiesManager.analyzeOpportunity('${opp.route}')"
                                class="text-green-600 hover:text-green-900 dark:text-green-400 dark:hover:text-green-300">
                            Analisar
                        </button>
                    ` : 'Monitorando'}
                </td>
            `;
            
            this.table.appendChild(row);
        });

        // Atualiza contadores com metadata
        this.updateCount(metadata.total_pairs || opportunities.length);
        this.updateLastUpdate();
    }

    formatRoute(route) {
        return route.replace(/→/g, ' → ');
    }

    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleTimeString();
    }

    updateCount(count) {
        if (this.countElement) {
            this.countElement.textContent = `${count} pares monitorados`;
        }
    }

    updateLastUpdate() {
        if (this.lastUpdateElement) {
            this.lastUpdateElement.textContent = `Última atualização: ${new Date().toLocaleTimeString()}`;
        }
    }

    showNoDataMessage() {
        if (!this.table.querySelector('.no-data-message')) {
            const row = document.createElement('tr');
            row.className = 'no-data-message';
            row.innerHTML = `
                <td colspan="7" class="px-6 py-12 text-center">
                    <div class="flex flex-col items-center justify-center space-y-3">
                        <svg class="w-12 h-12 text-gray-400 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        <p class="text-gray-500 dark:text-gray-400">
                            Nenhum par monitorado no momento
                        </p>
                    </div>
                </td>
            `;
            this.table.appendChild(row);
        }
    }

    monitorOpportunity(route) {
        window.realtimeMonitor.startMonitoring(route);
    }

    analyzeOpportunity(route) {
        window.opportunityAnalyzer.analyze(route);
    }
}

// Inicializa e exporta o gerenciador
const opportunitiesManager = new OpportunitiesManager();
window.opportunitiesManager = opportunitiesManager; // Para acesso global
export default opportunitiesManager;
