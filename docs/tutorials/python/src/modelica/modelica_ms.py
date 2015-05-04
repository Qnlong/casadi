#
#     This file is part of CasADi.
#
#     CasADi -- A symbolic framework for dynamic optimization.
#     Copyright (C) 2010-2014 Joel Andersson, Joris Gillis, Moritz Diehl,
#                             K.U. Leuven. All rights reserved.
#     Copyright (C) 2011-2014 Greg Horn
#
#     CasADi is free software; you can redistribute it and/or
#     modify it under the terms of the GNU Lesser General Public
#     License as published by the Free Software Foundation; either
#     version 3 of the License, or (at your option) any later version.
#
#     CasADi is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     Lesser General Public License for more details.
#
#     You should have received a copy of the GNU Lesser General Public
#     License along with CasADi; if not, write to the Free Software
#     Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
#
#$ \textbf{Direct multiple shooting with CasADi and JModelica.org}
#$ 
#$ To implement an optimal control solver for a Modelica model, let us begin by 
#$ retrieving the model equations from an FMUX object generated by JModelica.org.
#$ For this we extract the file modelDescription.xml from FMUX file as follows:
import zipfile
import os

fmux = zipfile.ZipFile("CSTR_CSTR_Opt2.fmux",'r')
fmux.extract('modelDescription.xml','.')
#$ This file can be imported into CasADi, building up a symbolic representation of the model
#$ The logic for importing Modelica models is located in the DaeBuilder class:
from casadi import *
ivp = DaeBuilder()
ivp.parseFMI("modelDescription.xml")
#! Let us have a look at the flat optimal control problem:
print ivp
#$ As we see, the initial-value problem (IVP) has two differential states (cstr.c and cstr.T),
#$ two algebraic variables (cstr.Tc and q) and one control.
#$
#$ By insprecting the equations, we see that it is relatively both straightforward to eliminate 
#$ the algebraic variables from the problem and to rewrite the DAE as an explicit ODE.
#$ Indeed, for cases like this one, CasADi can do this reformulation automatically:
ivp.makeExplicit()
#! Let us extract variables for the states, the control and equations
x = vertcat(ivp.x)
u = vertcat(ivp.u)
f = vertcat(ivp.ode)
L = vertcat(ivp.quad)
I = vertcat(ivp.init)
#$ These are expressions that can be visualized or manipulated using CasADi's 
#$ symbolic framework:
print 5*sin(f[0])
print jacobian(f,x)
print hessian(L,x)
#$ The efficient calculation of derivative information such as the Jacobians and Hessians above
#$ is one of the core strengths of CasADi. It is performed using state-of-the-art algorithms
#$ for \emph{algorithmic differentiation}. This allows for very large symbolic expressions
#$ to be handled efficiently. Another important observation is that all matrices in CasADi are
#$ \emph{sparse}. In the output above, it explains why the off-diagonal entries of the Hessian
#$ above are rendered as "00" -- it denotes a \emph{structural zero} of the matrix.
#$
#$ We can also retrieve other information from the model such as the end time,
#$ variable bounds and initial guess:
ubx = ivp.max(x)
lbx = ivp.min(x)
ubu = ivp.max(u)
lbu = ivp.min(u)
x0 = ivp.initialGuess(x)
u0 = ivp.initialGuess(u)
#$ Formulate the optimal control problem
tf = 150.
#$ We now proceeed to solve the optimal control problem, which can be written more compactly as:
#$  $$ \begin{array}{cl}   \textbf{minimize}    &  \displaystyle\int_{t=0}^{\texttt{tf}}{\texttt{L} \, dt} \\ \\
#$                         \textbf{subject to}  &  \texttt{I}(t) = 0, \quad \text{for} \quad t=0 \\
#$                                              &  \frac{d}{dt}{\texttt{x}} = \texttt{f}, \quad
#$                                                 \texttt{lbx} \le \texttt{x} \le \texttt{ubx}, \quad  
#$                                                 \texttt{lbu} \le \texttt{u} \le \texttt{ubu}, \quad 
#$                                                 \text{for} \quad 0 \le t \le \texttt{tf} 
#$ \end{array} $$
#$
#$ with
print "f = ", f, "\nI = ", I, "\nL = ", L
print "lbx = ", lbx, "ubx = ", ubx, "lbu = ", lbu, "ubu = ", ubu
#$ From the symbolic expressions, we can create functions (functors) for evaluating the 
#$ ODE right hand side numerically or symbolically. The following code creates a function
#$ with two inputs (x and u) and two outputs (f and L):
ode_fcn = MXFunction([x,u],[f,L])
ode_fcn.setOption("name","ode_fcn")
ode_fcn.init()
#$ We also create a function for evaluating the initial conditions:
init_fcn = MXFunction([x],[I])
init_fcn.setOption("name","init_fcn")
init_fcn.init()
#$ Increased speed is often possible by converting the MXFunction instances to SXFunction instances.
#$ This is possible when the symbolic expressions do not contain any exotic operators:
ode_fcn = SXFunction(ode_fcn)
ode_fcn.init()
init_fcn = SXFunction(init_fcn)
init_fcn.init()
#$ We shall use the "direct multiple shooting" method with 20 shooting intervals of equal length
#$ to solve the IVP. 
nk = 20
dt = tf/nk
#$ The first step of this method is to make a finite-dimensional representation of the control trajectory. 
#$ In our case, we shall assume that the control is constant on each interval.
#$ This allows us to transform the continuous-time optimal control problem into a discrete-time optimal control
#$ problem. In CasADi, we do this by creating a new function (functor) that given the state at the beginning 
#$ of the interval and the control gives the state at the end of the interval. This function thus solves an
#$ initial value problem in ODE (or DAE). We use the term "integrator" to refer to such a function. 
#$ Their evaluation can be done efficiently via
#$ algorithms for ODE/DAE integration implemented in CasADi or via interfaces to state-of-the-art codes
#$ such as SUNDIALS. These integrators and interfaces rely on CasADi's symbolic framework to automatically
#$ generate the (derivative) information needed by a particular solver, allowing fully automatic 
#$ (forward and adjoint) \emph{sensitivity analysis}, as explained in e.g. the SUNDIALS documentation.
#$
#$ It is also straightforward to implement one's own integrator in CasADi. A popular and efficient such 
#$ integrator, suitable for the problem at hand, is the (classical) Runge-Kutta (RK4) integrator.
#$ In this integrator, the ODE initial value problem is solved using the formula:
#$ \begin{itemize}
#$   \item $k_1 := f(t_n,x_n)$
#$   \item $k_2 := f(t_n + \frac{h}{2},x_n + \frac{h}{2} \, k_1)$
#$   \item $k_3 := f(t_n + \frac{h}{2},x_n + \frac{h}{2} \, k_2)$
#$   \item $k_4 := f(t_n + h,x_n + h \, k_3)$
#$ \end{itemize}
#$ where $h$ is the time-step. The state at $t_n + h$ is then given by:
#$ \begin{itemize}
#$   \item $x_{n+1} := x_n + \frac{1}{6}\left(k_1 + 2 \, k_2 + 2 \, k_3 + k_4\right) $
#$ \end{itemize}
#$ For more details, a good starting point is the Wikipedia entry on Runge-Kutta methods.
#$
#$ The CasADi code for implementing an integrator that takes 10 steps using the above method is:
nx = x.size1()
nu = u.size1()
nj = 10; h = dt/nj
xk = MX.sym("xk",nx)
uk = MX.sym("uk",nu)
xkj = xk; xkj_L = 0
for j in range(nj):
   [k1,k1_L] = ode_fcn([xkj,uk])
   [k2,k2_L] = ode_fcn([xkj + h/2*k1,uk])
   [k3,k3_L] = ode_fcn([xkj + h/2*k2,uk])
   [k4,k4_L] = ode_fcn([xkj + h*k3,uk])
   xkj   += h/6 * (k1   + 2*k2   + 2*k3   + k4)
   xkj_L += h/6 * (k1_L + 2*k2_L + 2*k3_L + k4_L)
integrator = MXFunction([xk,uk],[xkj,xkj_L])
integrator.setOption("name","integrator")
integrator.init()
#$ where we have applied the method both the the ODE and to the \emph{quadrature} $\frac{d}{dt}{x_{\text{L}}}(t) = L, \quad x_{\text{L}}(0) = 0$. The code above include "calls" the previously created ODE right-hand-side function (\verb|ode_fcn|).
#$
#$ The next step is to formulate a nonlinear program (NLP) for solving the discrete time optimal control problem. 
#$ CasADi works with NLPs of the form:
#$  $$ \begin{array}{cl}   \textbf{minimize}    &  f(x,p) \\
#$                         \textbf{subject to}  &  g_{\text{lb}} \le g(x,p) \le g_{\text{ub}},  \quad
#$                                                 \quad x_{\text{lb}} \le x \le x_{\text{ub}}
#$ \end{array} $$
#$ where $x$ is the decision variable and $p$ is a set of (known) parameters. In this formulation, a bound can set to
#$ $\pm \infty$ if absent and equality constraints are imposed by having upper and lower bounds equal to each other.
#$ 
#$ For the direct multiple shooting method, the degrees of freedom of the NLP are the parametrized controls and 
#$ the state at the beginning of each interval. We also include the state at the end time.
#$
#$ Let us declare symbolic primitives corresponding to these degrees of freedom:
xk = [MX.sym("x" + str(k), nx) for k in range(nk+1)]
uk = [MX.sym("u" + str(k), nu) for k in range(nk)]
#$ We gather all degrees of freedom of the NLP as well as bounds and initial guess for the decision variable:
v = []; lbv = []; ubv = []; v0 = []
#$ Length of v
nv = 0
#$ Indices corresponding to the different parts of the the variable vector:
vind = {'x':[], 'u':[]}
def valloc(n, nv): return range(nv, nv+n), nv+n
for k in range(nk):
   #$ States
   ind, nv = valloc(nx, nv)
   v.append(xk[k]); lbv.append(lbx); ubv.append(ubx); v0.append(x0); vind['x'].append(ind)
   #$ Control
   ind, nv = valloc(nu, nv)
   v.append(uk[k]); lbv.append(lbu); ubv.append(ubu); v0.append(u0); vind['u'].append(ind)
#$ State at end
ind, nv = valloc(nx, nv)
v.append(xk[-1]); lbv.append(lbx); ubv.append(ubx); v0.append(x0); vind['x'].append(ind)
#$ Concatenate lists
v = vertcat(v); lbv = vertcat(lbv); ubv = vertcat(ubv); v0 = vertcat(v0)
#$ Next, let us build up expressions for the objective (cost) function and the nonlinear constraints,
#$ starting with zero cost and and empty list of constraints:
J = 0;  eq = []
#$ We begin by adding to the NLP, the equations corresponding to the initial conditions. For this we
#$ "call" the above created \verb|init_fcn| with the expression for the state at the first interval:
[eq0] = init_fcn([xk[0]])
eq.append(eq0)
#$ Next, we loop over the shooting intervals, imposing continuity of the trajectory and summing up the
#$ the cost contributions:
for k in range(nk):
    [xk_end,Jk] = integrator([xk[k],uk[k]])
    J += Jk
    if k+1<nk: eq.append(xk_end - xk[k+1])
#$ Now form the NLP callback function and create an NLP solver. We shall use the open-source solver IPOPT
#$ which is able to solve large-scale NLPs efficiently. CasADi will automatically and efficiently generate
#$ the derivative information needed by IPOPT, including the Jacobian of the NLP constraints and the 
#$ Hessian of the Lagrangian function:
nlp = MXFunction(nlpIn(x=v),nlpOut(f=J,g=vertcat(eq)))
solver = NlpSolver("ipopt", nlp)
solver.init()
#$ Pass bounds on the variables and constraints. The upper and lower bounds on the equality constraints are 0:
solver.setInput(lbv,"lbx")
solver.setInput(ubv,"ubx")
solver.setInput(v0,"x0")
solver.setInput(0,"lbg")
solver.setInput(0,"ubg")
#$ Solving the NLP amounts to "evaluating the NLP solver":
solver.evaluate()
#$ After making sure that the solution was successful, we retrieve the solution:
v_opt  = solver.getOutput("x")
x0_opt = v_opt[[vind['x'][k][0] for k in range(nk+1)]]
x1_opt = v_opt[[vind['x'][k][1] for k in range(nk+1)]]
u_opt = v_opt[[vind['u'][k][0] for k in range(nk)]]
#$ Finally, we use the python package \emph{matplotlib} to visualize the solution. matplotlib uses a syntax
#$ which should look famliar to MATLAB users:
from pylab import *
from numpy import *
tgrid = linspace(0,tf,nk+1)
figure(1)
plot(tgrid,x0_opt)
title(str(x[0]))
grid()
show()
figure(2)
plot(tgrid,x1_opt)
title(str(x[1]))
grid()
show()
figure(3)
step(tgrid,vertcat((u_opt[0],u_opt)))
title(str(u))
grid()
show()
#$ CasADi is also able to generate self-contained C-code for evaluating the constructed functions.
#$ This can be useful for increasing execution speed or for evaluating expressions on embedded systems.
#$ As an example, the following code will generate C-code for the Hessian of the objective function
#$ with respect to the decision variables:
hess_f = nlp.hessian("x","f")
hess_f.init()
hess_f.generate("hess_f")
