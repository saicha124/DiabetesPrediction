import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report, f1_score

from federated_learning import FederatedLearningManager
from data_preprocessing import DataPreprocessor
from data_distribution import get_distribution_strategy, visualize_data_distribution
from utils import calculate_metrics, plot_confusion_matrix

# Page configuration
st.set_page_config(
    page_title="Agronomic Federated Learning Dashboard",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
def init_session_state():
    if 'training_started' not in st.session_state:
        st.session_state.training_started = False
    if 'training_completed' not in st.session_state:
        st.session_state.training_completed = False
    if 'results' not in st.session_state:
        st.session_state.results = None
    if 'fl_manager' not in st.session_state:
        st.session_state.fl_manager = None
    if 'training_metrics' not in st.session_state:
        st.session_state.training_metrics = []
    if 'confusion_matrices' not in st.session_state:
        st.session_state.confusion_matrices = []
    if 'execution_times' not in st.session_state:
        st.session_state.execution_times = []
    if 'communication_times' not in st.session_state:
        st.session_state.communication_times = []
    if 'client_status' not in st.session_state:
        st.session_state.client_status = {}
    if 'best_accuracy' not in st.session_state:
        st.session_state.best_accuracy = 0.0
    if 'early_stopped' not in st.session_state:
        st.session_state.early_stopped = False
    if 'current_round' not in st.session_state:
        st.session_state.current_round = 0
    if 'client_results' not in st.session_state:
        st.session_state.client_results = []
    if 'fog_results' not in st.session_state:
        st.session_state.fog_results = []
    if 'distribution_strategy' not in st.session_state:
        st.session_state.distribution_strategy = 'IID'
    if 'distribution_stats' not in st.session_state:
        st.session_state.distribution_stats = None

def start_training(data, num_clients, max_rounds, target_accuracy, 
                  aggregation_algorithm, enable_dp, epsilon, delta, committee_size,
                  distribution_strategy, strategy_params):
    """Start federated learning training with custom data distribution"""
    try:
        # Create FL manager
        st.session_state.fl_manager = FederatedLearningManager(
            num_clients=num_clients,
            max_rounds=max_rounds,
            target_accuracy=target_accuracy,
            aggregation_algorithm=aggregation_algorithm,
            enable_dp=enable_dp,
            epsilon=epsilon,
            delta=delta,
            committee_size=committee_size
        )
        
        # Store distribution configuration
        st.session_state.distribution_strategy = distribution_strategy
        st.session_state.strategy_params = strategy_params
        
        # Reset training state
        st.session_state.training_started = True
        st.session_state.training_completed = False
        st.session_state.training_metrics = []
        st.session_state.confusion_matrices = []
        st.session_state.execution_times = []
        st.session_state.communication_times = []
        st.session_state.client_status = {}
        st.session_state.best_accuracy = 0.0
        st.session_state.early_stopped = False
        st.session_state.current_round = 0
        st.session_state.client_results = []
        st.session_state.fog_results = []
        st.session_state.training_data = data
        
        st.success(f"Training initialized with {distribution_strategy} distribution! Switch to Live Monitoring tab to start.")
        
    except Exception as e:
        st.error(f"Error starting training: {str(e)}")

def run_training_loop(fl_manager, data):
    """Run the training loop with early stopping"""
    try:
        # Train with monitoring
        results = fl_manager.train(data)
        
        # Store results in session state with safe access
        try:
            st.session_state.results = results
            st.session_state.training_completed = True
            st.session_state.training_started = False
            
            # Extract client and fog results for tables
            extract_training_results(fl_manager)
        except Exception as session_error:
            print(f"Session state update failed: {session_error}")
            # Store results in the fl_manager for later retrieval
            fl_manager.final_results = results
            fl_manager.training_completed = True
        
    except Exception as e:
        try:
            st.session_state.training_started = False
        except:
            pass
        print(f"Training failed: {str(e)}")

def extract_training_results(fl_manager):
    """Extract detailed client and fog results for tabular display"""
    client_results = []
    fog_results = []
    
    # Extract client metrics
    for i, client in enumerate(fl_manager.clients):
        if hasattr(client, 'training_history') and client.training_history:
            latest_metrics = client.training_history[-1]
            client_results.append({
                'Station ID': f'Field-{i+1}',
                'Samples': latest_metrics.get('samples', 0),
                'Accuracy': f"{latest_metrics.get('test_accuracy', 0):.3f}",
                'F1 Score': f"{latest_metrics.get('f1_score', 0):.3f}",
                'Training Time': f"{latest_metrics.get('training_time', 0):.2f}s",
                'Classes': latest_metrics.get('classes', 0),
                'Status': 'Active' if latest_metrics.get('test_accuracy', 0) > 0 else 'Inactive'
            })
    
    # Extract fog-level aggregation results
    for round_num in range(len(st.session_state.training_metrics)):
        metrics = st.session_state.training_metrics[round_num]
        fog_results.append({
            'Round': round_num + 1,
            'Global Accuracy': f"{metrics.get('accuracy', 0):.3f}",
            'Global F1': f"{metrics.get('f1_score', 0):.3f}",
            'Aggregation Time': f"{st.session_state.execution_times[round_num] if round_num < len(st.session_state.execution_times) else 0:.2f}s",
            'Communication Time': f"{st.session_state.communication_times[round_num] if round_num < len(st.session_state.communication_times) else 0:.2f}s",
            'Algorithm': st.session_state.fl_manager.aggregation_algorithm,
            'Privacy': 'Enabled' if st.session_state.fl_manager.enable_dp else 'Disabled'
        })
    
    st.session_state.client_results = client_results
    st.session_state.fog_results = fog_results

def show_training_progress():
    """Display real-time training progress"""
    st.header("📊 Live Training Progress")
    
    # Update session state from fl_manager if available
    if st.session_state.fl_manager:
        # Sync data from fl_manager to session state
        if hasattr(st.session_state.fl_manager, 'training_history'):
            st.session_state.training_metrics = st.session_state.fl_manager.training_history
        if hasattr(st.session_state.fl_manager, 'confusion_matrices'):
            st.session_state.confusion_matrices = st.session_state.fl_manager.confusion_matrices
        if hasattr(st.session_state.fl_manager, 'execution_times'):
            st.session_state.execution_times = st.session_state.fl_manager.execution_times
        if hasattr(st.session_state.fl_manager, 'communication_times'):
            st.session_state.communication_times = st.session_state.fl_manager.communication_times
        if hasattr(st.session_state.fl_manager, 'best_accuracy'):
            st.session_state.best_accuracy = st.session_state.fl_manager.best_accuracy
        if hasattr(st.session_state.fl_manager, 'early_stopped'):
            st.session_state.early_stopped = st.session_state.fl_manager.early_stopped
        if hasattr(st.session_state.fl_manager, 'training_completed'):
            st.session_state.training_completed = st.session_state.fl_manager.training_completed
    
    # Overall progress
    progress_col1, progress_col2, progress_col3 = st.columns(3)
    
    with progress_col1:
        if st.session_state.fl_manager:
            current_round = getattr(st.session_state.fl_manager, 'current_round', 0)
            max_rounds = st.session_state.fl_manager.max_rounds
            progress = min(current_round / max_rounds, 1.0) if max_rounds > 0 else 0
            st.metric("Training Round", f"{current_round}/{max_rounds}")
            st.progress(progress)
    
    with progress_col2:
        current_accuracy = getattr(st.session_state, 'best_accuracy', 0.0)
        target_accuracy = st.session_state.fl_manager.target_accuracy if st.session_state.fl_manager else 0.85
        st.metric("Best Accuracy", f"{current_accuracy:.3f}")
        st.metric("Target", f"{target_accuracy:.3f}")
    
    with progress_col3:
        early_stopped = getattr(st.session_state, 'early_stopped', False)
        training_completed = getattr(st.session_state, 'training_completed', False)
        
        if early_stopped:
            st.success("🎯 Target Accuracy Reached!")
        elif training_completed:
            st.info("✅ Training Completed")
        else:
            st.info("🔄 Training in Progress")
    
    # Field station status (simulate based on current round)
    if st.session_state.fl_manager:
        st.subheader("🏢 Field Station Status")
        
        num_clients = st.session_state.fl_manager.num_clients
        cols = st.columns(min(5, num_clients))
        
        for i in range(num_clients):
            with cols[i % len(cols)]:
                if training_completed or early_stopped:
                    status_color = "🟢"
                    status = "Completed"
                else:
                    status_color = "🟡"
                    status = "Training"
                st.metric(f"Station {i+1}", f"{status_color} {status}")

def show_training_charts():
    """Display advanced training progress visualizations"""
    if not st.session_state.training_metrics:
        return
    
    st.header("📈 Real-Time Training Analytics")
    
    # Create metrics dataframe
    metrics_df = pd.DataFrame(st.session_state.training_metrics)
    
    # Main performance chart with multiple metrics
    col1, col2 = st.columns(2)
    
    with col1:
        # Multi-metric performance chart
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Model Performance', 'Training Loss'),
            vertical_spacing=0.1
        )
        
        # Performance metrics
        if 'accuracy' in metrics_df.columns:
            fig.add_trace(go.Scatter(
                x=list(range(1, len(metrics_df) + 1)),
                y=metrics_df['accuracy'],
                mode='lines+markers',
                name='Accuracy',
                line=dict(color='#2E86AB', width=3),
                marker=dict(size=8)
            ), row=1, col=1)
            
        if 'f1_score' in metrics_df.columns:
            fig.add_trace(go.Scatter(
                x=list(range(1, len(metrics_df) + 1)),
                y=metrics_df['f1_score'],
                mode='lines+markers',
                name='F1 Score',
                line=dict(color='#A23B72', width=3),
                marker=dict(size=8)
            ), row=1, col=1)
        
        # Add target accuracy line
        if st.session_state.fl_manager:
            target = st.session_state.fl_manager.target_accuracy
            fig.add_hline(y=target, line_dash="dash", line_color="red", 
                         annotation_text=f"Target: {target:.3f}", row=1, col=1)
        
        # Loss chart
        if 'loss' in metrics_df.columns:
            fig.add_trace(go.Scatter(
                x=list(range(1, len(metrics_df) + 1)),
                y=metrics_df['loss'],
                mode='lines+markers',
                name='Loss',
                line=dict(color='#F18F01', width=3),
                marker=dict(size=8)
            ), row=2, col=1)
        
        fig.update_layout(
            height=600,
            title_text="Training Performance Metrics",
            template="plotly_white",
            showlegend=True
        )
        fig.update_xaxes(title_text="Training Round")
        fig.update_yaxes(title_text="Score", row=1, col=1)
        fig.update_yaxes(title_text="Loss", row=2, col=1)
        
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Execution time analysis
        if st.session_state.execution_times:
            fig_time = go.Figure()
            
            # Bar chart for execution times
            fig_time.add_trace(go.Bar(
                x=list(range(1, len(st.session_state.execution_times) + 1)),
                y=st.session_state.execution_times,
                name='Execution Time',
                marker_color='#C73E1D',
                text=[f'{t:.2f}s' for t in st.session_state.execution_times],
                textposition='auto'
            ))
            
            # Add average line
            avg_time = np.mean(st.session_state.execution_times)
            fig_time.add_hline(y=avg_time, line_dash="dash", line_color="green",
                              annotation_text=f"Avg: {avg_time:.2f}s")
            
            fig_time.update_layout(
                title="Training Time per Round",
                xaxis_title="Training Round",
                yaxis_title="Time (seconds)",
                template="plotly_white",
                height=300
            )
            st.plotly_chart(fig_time, use_container_width=True)
        
        # Communication overhead visualization
        if st.session_state.communication_times:
            fig_comm = go.Figure()
            
            fig_comm.add_trace(go.Scatter(
                x=list(range(1, len(st.session_state.communication_times) + 1)),
                y=st.session_state.communication_times,
                mode='lines+markers',
                name='Communication Time',
                line=dict(color='#3F7CAC', width=2),
                fill='tonexty',
                fillcolor='rgba(63, 124, 172, 0.1)'
            ))
            
            fig_comm.update_layout(
                title="Communication Overhead",
                xaxis_title="Training Round",
                yaxis_title="Time (seconds)",
                template="plotly_white",
                height=250
            )
            st.plotly_chart(fig_comm, use_container_width=True)
    
    # Advanced analytics section
    st.subheader("🔍 Advanced Analytics")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Convergence analysis
        if len(metrics_df) > 1:
            accuracy_trend = np.diff(metrics_df['accuracy']) if 'accuracy' in metrics_df.columns else []
            convergence_rate = np.mean(accuracy_trend) if len(accuracy_trend) > 0 else 0
            
            fig_conv = go.Figure()
            fig_conv.add_trace(go.Scatter(
                x=list(range(2, len(metrics_df) + 1)),
                y=accuracy_trend,
                mode='lines+markers',
                name='Accuracy Change',
                line=dict(color='purple', width=2)
            ))
            fig_conv.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_conv.update_layout(
                title=f"Convergence Rate: {convergence_rate:.4f}",
                xaxis_title="Round",
                yaxis_title="Accuracy Change",
                template="plotly_white",
                height=300
            )
            st.plotly_chart(fig_conv, use_container_width=True)
    
    with col2:
        # Efficiency metrics
        if st.session_state.execution_times and 'accuracy' in metrics_df.columns:
            efficiency = metrics_df['accuracy'] / np.array(st.session_state.execution_times)
            
            fig_eff = go.Figure()
            fig_eff.add_trace(go.Bar(
                x=list(range(1, len(efficiency) + 1)),
                y=efficiency,
                name='Efficiency',
                marker_color='lightgreen',
                text=[f'{e:.3f}' for e in efficiency],
                textposition='auto'
            ))
            fig_eff.update_layout(
                title="Training Efficiency (Accuracy/Time)",
                xaxis_title="Round",
                yaxis_title="Efficiency Score",
                template="plotly_white",
                height=300
            )
            st.plotly_chart(fig_eff, use_container_width=True)
    
    with col3:
        # Performance distribution
        if 'accuracy' in metrics_df.columns and len(metrics_df) > 2:
            fig_dist = go.Figure()
            fig_dist.add_trace(go.Histogram(
                x=metrics_df['accuracy'],
                nbinsx=10,
                name='Accuracy Distribution',
                marker_color='orange',
                opacity=0.7
            ))
            fig_dist.update_layout(
                title="Accuracy Distribution",
                xaxis_title="Accuracy",
                yaxis_title="Frequency",
                template="plotly_white",
                height=300
            )
            st.plotly_chart(fig_dist, use_container_width=True)

def show_results():
    """Display final training results in tables"""
    st.header("📋 Training Results Analysis")
    
    if not st.session_state.results:
        return
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        final_accuracy = st.session_state.results.get('accuracy', 0)
        st.metric("Final Accuracy", f"{final_accuracy:.3f}")
    
    with col2:
        final_f1 = st.session_state.results.get('f1_score', 0)
        st.metric("Final F1 Score", f"{final_f1:.3f}")
    
    with col3:
        total_rounds = len(st.session_state.training_metrics)
        st.metric("Total Rounds", total_rounds)
    
    with col4:
        total_time = sum(st.session_state.execution_times) if st.session_state.execution_times else 0
        st.metric("Total Time", f"{total_time:.1f}s")
    
    # Results tables
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🏢 Field Station Results")
        if st.session_state.client_results:
            client_df = pd.DataFrame(st.session_state.client_results)
            st.dataframe(client_df, use_container_width=True)
        else:
            st.info("No client results available")
    
    with col2:
        st.subheader("🌐 Fog Aggregation Results")
        if st.session_state.fog_results:
            fog_df = pd.DataFrame(st.session_state.fog_results)
            st.dataframe(fog_df, use_container_width=True)
        else:
            st.info("No fog results available")

def make_prediction(sample_data):
    """Make prediction for crop sample data"""
    if st.session_state.fl_manager and hasattr(st.session_state.fl_manager, 'global_model') and st.session_state.fl_manager.global_model is not None:
        try:
            # Use the fitted preprocessor from the federated learning manager
            if hasattr(st.session_state.fl_manager, 'preprocessor') and st.session_state.fl_manager.preprocessor.is_fitted:
                processed_data = st.session_state.fl_manager.preprocessor.transform(sample_data)
            else:
                # Fallback: create temporary preprocessor and fit on available data
                preprocessor = DataPreprocessor()
                # Load the diabetes dataset to fit the preprocessor
                data = pd.read_csv('diabetes.csv')
                X, y = preprocessor.fit_transform(data)
                processed_data = preprocessor.transform(sample_data)
            
            # Make prediction
            prediction = st.session_state.fl_manager.global_model.predict(processed_data)[0]
            probability = st.session_state.fl_manager.global_model.predict_proba(processed_data)[0][1]
            
            return prediction, probability
        
        except Exception as e:
            st.error(f"Prediction error: {str(e)}")
            return 0, 0.0
    
    return 0, 0.0

def reset_training():
    """Reset training state"""
    st.session_state.training_started = False
    st.session_state.training_completed = False
    st.session_state.results = None
    st.session_state.fl_manager = None
    st.session_state.training_metrics = []
    st.session_state.confusion_matrices = []
    st.session_state.execution_times = []
    st.session_state.communication_times = []
    st.session_state.client_status = {}
    st.session_state.best_accuracy = 0.0
    st.session_state.early_stopped = False
    st.session_state.current_round = 0
    st.session_state.client_results = []
    st.session_state.fog_results = []

def main():
    init_session_state()
    
    st.title("🌾 Agronomic Display - Hierarchical Federated Learning")
    st.markdown("**Advanced Crop Health Analytics & Prediction System**")
    st.markdown("---")
    
    # Data loading and preprocessing
    try:
        data = pd.read_csv('diabetes.csv')
        preprocessor = DataPreprocessor()
        X, y = preprocessor.fit_transform(data)
        
        st.success(f"✅ Field Data loaded: {len(data)} crop samples with {len(data.columns)} health indicators")
        
        # Display data overview in agronomic terms
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🌱 Field Samples", len(data))
        with col2:
            st.metric("📊 Health Indicators", len(data.columns) - 1)
        with col3:
            positive_ratio = (data['Outcome'] == 1).mean()
            st.metric("🚨 Risk Cases", f"{positive_ratio:.1%}")
            
    except Exception as e:
        st.error(f"❌ Error loading field data: {str(e)}")
        return
    
    # Multi-tab interface
    tab1, tab2, tab3, tab4 = st.tabs(["🎛️ Training Control", "📈 Live Monitoring", "📋 Results Analysis", "🔍 Risk Prediction"])
    
    with tab1:
        st.header("🎛️ Federated Training Configuration")
        
        # Create three columns for better organization
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("📊 Basic Settings")
            num_clients = st.slider("🏢 Number of Field Stations", min_value=3, max_value=10, value=5)
            max_rounds = st.slider("🔄 Maximum Training Cycles", min_value=5, max_value=50, value=20)
            target_accuracy = st.slider("🎯 Target Accuracy (Auto-Stop)", min_value=0.7, max_value=0.95, value=0.85, step=0.05)
            
        with col2:
            st.subheader("🔧 Algorithm Settings")
            aggregation_algorithm = st.selectbox("Aggregation Algorithm", ["FedAvg", "FedProx", "SecureAgg"])
            enable_dp = st.checkbox("🔒 Enable Privacy Protection", value=True)
            if enable_dp:
                epsilon = st.number_input("🛡️ Privacy Budget (ε)", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
                delta = st.number_input("🔐 Privacy Parameter (δ)", min_value=1e-6, max_value=1e-3, value=1e-5, format="%.1e")
            else:
                epsilon = delta = None
            committee_size = st.slider("👥 Security Committee Size", min_value=2, max_value=5, value=3)
        
        with col3:
            st.subheader("🌍 Data Distribution Strategy")
            distribution_strategy = st.selectbox(
                "Distribution Pattern",
                ["IID", "Non-IID (Dirichlet)", "Pathological Non-IID", "Quantity Skew", "Geographic"],
                index=0
            )
            
            # Strategy-specific parameters
            strategy_params = {}
            if distribution_strategy == "Non-IID (Dirichlet)":
                alpha = st.slider("Alpha (Non-IID strength)", min_value=0.1, max_value=2.0, value=0.5, step=0.1)
                strategy_params['alpha'] = alpha
                st.info("Lower alpha = more non-IID")
            elif distribution_strategy == "Pathological Non-IID":
                classes_per_client = st.slider("Classes per Station", min_value=1, max_value=2, value=1)
                strategy_params['classes_per_client'] = classes_per_client
            elif distribution_strategy == "Quantity Skew":
                skew_factor = st.slider("Skew Factor", min_value=0.5, max_value=3.0, value=2.0, step=0.1)
                strategy_params['skew_factor'] = skew_factor
                st.info("Higher factor = more skewed")
            elif distribution_strategy == "Geographic":
                correlation_strength = st.slider("Geographic Correlation", min_value=0.1, max_value=1.0, value=0.8, step=0.1)
                strategy_params['correlation_strength'] = correlation_strength
            
            st.session_state.distribution_strategy = distribution_strategy
            st.session_state.strategy_params = strategy_params
        
        # Data distribution preview
        st.subheader("📈 Data Distribution Preview")
        if st.button("🔍 Preview Data Distribution"):
            with st.spinner("Generating distribution preview..."):
                try:
                    # Create distribution strategy
                    strategy = get_distribution_strategy(
                        distribution_strategy, 
                        num_clients, 
                        random_state=42,
                        **strategy_params
                    )
                    
                    # Apply distribution
                    client_data = strategy.distribute_data(X, y)
                    distribution_stats = strategy.get_distribution_stats(client_data)
                    
                    # Store for later use
                    st.session_state.distribution_stats = distribution_stats
                    st.session_state.preview_client_data = client_data
                    
                    # Create visualizations
                    fig_sizes, fig_heatmap = visualize_data_distribution(client_data, distribution_stats)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.plotly_chart(fig_sizes, use_container_width=True)
                    with col2:
                        st.plotly_chart(fig_heatmap, use_container_width=True)
                    
                    # Display statistics
                    st.subheader("Distribution Statistics")
                    stats_col1, stats_col2, stats_col3 = st.columns(3)
                    
                    with stats_col1:
                        st.metric("Strategy", distribution_stats['strategy'])
                        st.metric("Total Samples", distribution_stats['total_samples'])
                    
                    with stats_col2:
                        avg_size = np.mean(distribution_stats['client_sizes'])
                        std_size = np.std(distribution_stats['client_sizes'])
                        st.metric("Avg Station Size", f"{avg_size:.1f}")
                        st.metric("Size Std Dev", f"{std_size:.1f}")
                    
                    with stats_col3:
                        min_size = min(distribution_stats['client_sizes'])
                        max_size = max(distribution_stats['client_sizes'])
                        st.metric("Min Station Size", min_size)
                        st.metric("Max Station Size", max_size)
                    
                    st.success("Distribution preview generated successfully!")
                    
                except Exception as e:
                    st.error(f"Error generating preview: {str(e)}")
        
        # Training controls
        st.subheader("🚀 Training Controls")
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.button("🚀 Start Federated Learning", disabled=st.session_state.training_started):
                start_training(data, num_clients, max_rounds, target_accuracy, 
                              aggregation_algorithm, enable_dp, epsilon, delta, committee_size,
                              distribution_strategy, strategy_params)
        
        with col2:
            if st.button("🔄 Reset System"):
                reset_training()
                st.rerun()
    
    with tab2:
        st.header("📈 Live Training Monitoring")
        
        # Direct training execution
        if st.session_state.training_started and not st.session_state.training_completed:
            if hasattr(st.session_state, 'training_data') and st.session_state.fl_manager:
                st.info("🔄 Starting federated learning training...")
                
                # Create progress containers
                progress_container = st.empty()
                metrics_container = st.empty()
                charts_container = st.empty()
                
                # Run training with real-time updates
                try:
                    fl_manager = st.session_state.fl_manager
                    data = st.session_state.training_data
                    
                    # Apply custom data distribution
                    distribution_strategy = getattr(st.session_state, 'distribution_strategy', 'IID')
                    strategy_params = getattr(st.session_state, 'strategy_params', {})
                    
                    # Create distribution strategy
                    strategy = get_distribution_strategy(
                        distribution_strategy, 
                        fl_manager.num_clients, 
                        random_state=42,
                        **strategy_params
                    )
                    
                    # Preprocess data
                    preprocessor = DataPreprocessor()
                    X, y = preprocessor.fit_transform(data)
                    
                    # Apply distribution
                    client_data = strategy.distribute_data(X, y)
                    distribution_stats = strategy.get_distribution_stats(client_data)
                    
                    # Store distribution stats
                    st.session_state.distribution_stats = distribution_stats
                    
                    # Setup clients with distributed data
                    fl_manager.setup_clients_with_data(client_data)
                    
                    # Training loop
                    for round_num in range(fl_manager.max_rounds):
                        current_round = round_num + 1
                        
                        # Update progress
                        with progress_container.container():
                            st.subheader(f"Round {current_round}/{fl_manager.max_rounds}")
                            progress_bar = st.progress(current_round / fl_manager.max_rounds)
                            
                            # Field station status
                            cols = st.columns(fl_manager.num_clients)
                            for i in range(fl_manager.num_clients):
                                with cols[i]:
                                    st.metric(f"Station {i+1}", "🟡 Training")
                        
                        # Run training round
                        start_time = time.time()
                        
                        # Train clients
                        client_updates = fl_manager._train_clients_parallel()
                        
                        # Aggregate
                        fl_manager.global_model = fl_manager.aggregator.aggregate(
                            fl_manager.global_model, client_updates
                        )
                        
                        # Evaluate
                        accuracy, loss, f1, cm = fl_manager._evaluate_global_model()
                        
                        round_time = time.time() - start_time
                        
                        # Store metrics
                        metrics = {
                            'round': current_round,
                            'accuracy': accuracy,
                            'loss': loss,
                            'f1_score': f1,
                            'execution_time': round_time
                        }
                        
                        st.session_state.training_metrics.append(metrics)
                        st.session_state.execution_times.append(round_time)
                        st.session_state.confusion_matrices.append(cm)
                        st.session_state.communication_times.append(0.5)
                        st.session_state.best_accuracy = max(st.session_state.best_accuracy, accuracy)
                        st.session_state.current_round = current_round
                        
                        # Update metrics display
                        with metrics_container.container():
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Accuracy", f"{accuracy:.3f}")
                            with col2:
                                st.metric("F1 Score", f"{f1:.3f}")
                            with col3:
                                st.metric("Best Accuracy", f"{st.session_state.best_accuracy:.3f}")
                        
                        # Update charts
                        with charts_container.container():
                            if len(st.session_state.training_metrics) > 1:
                                show_training_charts()
                        
                        # Check early stopping
                        if accuracy >= fl_manager.target_accuracy:
                            st.success(f"🎯 Target accuracy {fl_manager.target_accuracy:.3f} reached!")
                            st.session_state.early_stopped = True
                            break
                        
                        # Update station status to completed
                        with progress_container.container():
                            st.subheader(f"Round {current_round}/{fl_manager.max_rounds}")
                            progress_bar = st.progress(current_round / fl_manager.max_rounds)
                            
                            cols = st.columns(fl_manager.num_clients)
                            for i in range(fl_manager.num_clients):
                                with cols[i]:
                                    st.metric(f"Station {i+1}", "🟢 Completed")
                        
                        time.sleep(1)  # Brief pause between rounds
                    
                    # Training completed
                    st.session_state.training_completed = True
                    st.session_state.training_started = False
                    
                    # Final results
                    final_accuracy = st.session_state.best_accuracy
                    st.session_state.results = {
                        'accuracy': final_accuracy,
                        'f1_score': f1,
                        'rounds_completed': current_round,
                        'early_stopped': st.session_state.early_stopped,
                        'training_history': st.session_state.training_metrics
                    }
                    
                    # Extract results for tables
                    extract_training_results(fl_manager)
                    
                    st.success("Training completed successfully!")
                    
                except Exception as e:
                    st.error(f"Training failed: {str(e)}")
                    st.session_state.training_started = False
            else:
                st.warning("Please start training from the Training Control tab first.")
        
        # Show completed training results
        elif st.session_state.training_completed:
            st.success("✅ Training Completed")
            show_training_progress()
            if len(st.session_state.training_metrics) > 0:
                show_training_charts()
        else:
            st.info("🌱 Start training to see live monitoring data")
    
    with tab3:
        st.header("📋 Training Results Analysis")
        
        # Results
        if st.session_state.training_completed and st.session_state.results:
            show_results()
        else:
            st.info("🌾 Complete training to see detailed results analysis")
    
    with tab4:
        st.header("🔍 Crop Health Risk Prediction")
        
        if st.session_state.training_completed and st.session_state.results:
            # Prediction examples section
            st.subheader("📝 Example Predictions")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 🟢 Low Risk Example")
                if st.button("Test Low Risk Sample"):
                    # Low risk example data
                    low_risk_data = pd.DataFrame({
                        'Pregnancies': [1],
                        'Glucose': [85],
                        'BloodPressure': [66],
                        'SkinThickness': [29],
                        'Insulin': [0],
                        'BMI': [26.6],
                        'DiabetesPedigreeFunction': [0.351],
                        'Age': [31]
                    })
                    
                    prediction, probability = make_prediction(low_risk_data)
                    
                    st.success(f"**Prediction:** {'High Risk' if prediction == 1 else 'Low Risk'}")
                    st.metric("Risk Probability", f"{probability:.1%}")
                    st.json(low_risk_data.iloc[0].to_dict())
            
            with col2:
                st.markdown("### 🔴 High Risk Example")
                if st.button("Test High Risk Sample"):
                    # High risk example data
                    high_risk_data = pd.DataFrame({
                        'Pregnancies': [6],
                        'Glucose': [148],
                        'BloodPressure': [72],
                        'SkinThickness': [35],
                        'Insulin': [0],
                        'BMI': [33.6],
                        'DiabetesPedigreeFunction': [0.627],
                        'Age': [50]
                    })
                    
                    prediction, probability = make_prediction(high_risk_data)
                    
                    if prediction == 1:
                        st.error(f"**Prediction:** High Risk")
                    else:
                        st.success(f"**Prediction:** Low Risk")
                    st.metric("Risk Probability", f"{probability:.1%}")
                    st.json(high_risk_data.iloc[0].to_dict())
            
            st.markdown("---")
            
            # Custom prediction interface
            st.subheader("🧪 Custom Field Sample Analysis")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Growth Conditions**")
                pregnancies = st.number_input("Growth Cycles", min_value=0, max_value=20, value=1)
                glucose = st.number_input("Nutrient Level", min_value=0, max_value=300, value=120)
                blood_pressure = st.number_input("Soil Pressure", min_value=0, max_value=200, value=80)
                skin_thickness = st.number_input("Leaf Thickness", min_value=0, max_value=100, value=20)
                
            with col2:
                st.markdown("**Environmental Factors**")
                insulin = st.number_input("Water Content", min_value=0, max_value=900, value=80)
                bmi = st.number_input("Plant Density Index", min_value=0.0, max_value=70.0, value=25.0, step=0.1)
                diabetes_pedigree = st.number_input("Genetic Risk Factor", min_value=0.0, max_value=3.0, value=0.5, step=0.01)
                age = st.number_input("Plant Maturity (days)", min_value=18, max_value=120, value=30)
            
            if st.button("🔬 Analyze Crop Sample"):
                # Create sample data
                sample_data = pd.DataFrame({
                    'Pregnancies': [pregnancies],
                    'Glucose': [glucose],
                    'BloodPressure': [blood_pressure],
                    'SkinThickness': [skin_thickness],
                    'Insulin': [insulin],
                    'BMI': [bmi],
                    'DiabetesPedigreeFunction': [diabetes_pedigree],
                    'Age': [age]
                })
                
                prediction, probability = make_prediction(sample_data)
                
                # Display prediction
                col1, col2 = st.columns(2)
                with col1:
                    risk_level = "High Risk" if prediction == 1 else "Low Risk"
                    color = "red" if prediction == 1 else "green"
                    st.markdown(f"### Crop Status: <span style='color: {color}'>{risk_level}</span>", unsafe_allow_html=True)
                    
                with col2:
                    st.metric("Risk Probability", f"{probability:.1%}")
                    
                # Risk interpretation
                if probability > 0.7:
                    st.warning("🚨 High disease risk detected. Recommend immediate field intervention.")
                elif probability > 0.3:
                    st.info("⚠️ Moderate risk. Consider preventive treatments and increased monitoring.")
                else:
                    st.success("✅ Healthy crop status. Continue current care protocols.")
        else:
            st.info("🌾 Complete training to enable crop risk prediction")

if __name__ == "__main__":
    main()